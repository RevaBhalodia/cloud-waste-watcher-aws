data "aws_caller_identity" "current" {}

# ---------------------------------------------------------------------------
# Code: one zip from src/, used by both Lambda functions.
# ---------------------------------------------------------------------------
data "archive_file" "code" {
  type        = "zip"
  source_dir  = "${path.module}/../src"
  output_path = "${path.module}/build/waste-watcher.zip"
  excludes    = ["price_lookup.py", "__pycache__"]
}

# ---------------------------------------------------------------------------
# Storage: DynamoDB in PROVISIONED mode, because only provisioned capacity is
# covered by the always-free allowance. Auto scaling is simply not configured.
# ---------------------------------------------------------------------------
resource "aws_dynamodb_table" "findings" {
  name           = "${var.name}-findings"
  billing_mode   = "PROVISIONED"
  read_capacity  = 5
  write_capacity = 5
  hash_key       = "pk"
  range_key      = "sk"

  attribute {
    name = "pk"
    type = "S"
  }
  attribute {
    name = "sk"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}

# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
resource "aws_sns_topic" "digest" {
  name = "${var.name}-digest"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.digest.arn
  protocol  = "email"
  endpoint  = var.notification_email
}

# ---------------------------------------------------------------------------
# Scanner Lambda + its least-privilege role
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scanner" {
  name               = "${var.name}-scanner-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

resource "aws_iam_role_policy_attachment" "scanner_logs" {
  role       = aws_iam_role.scanner.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "scanner" {
  # Describe calls cannot be limited to single resources, so "*" is correct here.
  # The protection is that every action is read-only.
  statement {
    sid       = "ReadOnlyScan"
    actions   = ["ec2:DescribeVolumes", "ec2:DescribeAddresses", "ec2:DescribeInstances", "ec2:DescribeSnapshots"]
    resources = ["*"]
  }
  statement {
    sid       = "SaveAndReadHistory"
    actions   = ["dynamodb:BatchWriteItem", "dynamodb:PutItem", "dynamodb:Query"]
    resources = [aws_dynamodb_table.findings.arn]
  }
  statement {
    sid       = "SendDigest"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.digest.arn]
  }
}

resource "aws_iam_role_policy" "scanner" {
  name   = "scanner-permissions"
  role   = aws_iam_role.scanner.id
  policy = data.aws_iam_policy_document.scanner.json
}

resource "aws_lambda_function" "scanner" {
  function_name    = "${var.name}-scan"
  role             = aws_iam_role.scanner.arn
  runtime          = var.lambda_runtime
  handler          = "lambda_function.lambda_handler"
  filename         = data.archive_file.code.output_path
  source_code_hash = data.archive_file.code.output_base64sha256
  timeout          = 30
  memory_size      = 128

  environment {
    variables = {
      TABLE_NAME = aws_dynamodb_table.findings.name
      TOPIC_ARN  = aws_sns_topic.digest.arn
    }
  }

  depends_on = [aws_iam_role_policy_attachment.scanner_logs]
}

# ---------------------------------------------------------------------------
# Daily schedule (EventBridge Scheduler)
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "scheduler_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${var.name}-scheduler-role"
  assume_role_policy = data.aws_iam_policy_document.scheduler_trust.json
}

resource "aws_iam_role_policy" "scheduler" {
  name = "invoke-scanner"
  role = aws_iam_role.scheduler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = aws_lambda_function.scanner.arn
    }]
  })
}

resource "aws_scheduler_schedule" "daily" {
  name                         = "${var.name}-daily"
  schedule_expression          = var.schedule_expression
  schedule_expression_timezone = var.schedule_timezone

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.scanner.arn
    role_arn = aws_iam_role.scheduler.arn
  }
}

# ---------------------------------------------------------------------------
# Dashboard API Lambda: its own role that can ONLY read the table.
# ---------------------------------------------------------------------------
resource "aws_iam_role" "api" {
  name               = "${var.name}-api-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

resource "aws_iam_role_policy_attachment" "api_logs" {
  role       = aws_iam_role.api.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "api" {
  name = "read-findings"
  role = aws_iam_role.api.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "dynamodb:Query"
      Resource = aws_dynamodb_table.findings.arn
    }]
  })
}

resource "aws_lambda_function" "api" {
  function_name    = "${var.name}-api"
  role             = aws_iam_role.api.arn
  runtime          = var.lambda_runtime
  handler          = "api_function.lambda_handler"
  filename         = data.archive_file.code.output_path
  source_code_hash = data.archive_file.code.output_base64sha256
  timeout          = 10
  memory_size      = 128

  environment {
    variables = {
      TABLE_NAME      = aws_dynamodb_table.findings.name
      DASHBOARD_TOKEN = var.dashboard_token
    }
  }

  depends_on = [aws_iam_role_policy_attachment.api_logs]
}

resource "aws_lambda_function_url" "api" {
  function_name      = aws_lambda_function.api.function_name
  authorization_type = "NONE" # the bearer token in api_function.py is the lock

  cors {
    allow_origins = [var.allowed_origin]
    allow_headers = ["authorization"]
    allow_methods = ["GET"]
  }
}

# Since Oct 2025 a public function URL needs BOTH of these permissions.
resource "aws_lambda_permission" "url_invoke_url" {
  statement_id           = "AllowPublicInvokeFunctionUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.api.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

resource "aws_lambda_permission" "url_invoke_function" {
  statement_id             = "AllowPublicInvokeFunctionViaUrl"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.api.function_name
  principal                = "*"
  invoked_via_function_url = true
}
