output "dashboard_api_url" {
  description = "Paste this into API_URL in dashboard/index.html"
  value       = aws_lambda_function_url.api.function_url
}

output "table_name" {
  value = aws_dynamodb_table.findings.name
}

output "topic_arn" {
  value = aws_sns_topic.digest.arn
}
