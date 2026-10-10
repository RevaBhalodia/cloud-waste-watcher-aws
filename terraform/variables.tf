variable "region" {
  description = "Region the stack is deployed to (and the region that gets scanned)."
  type        = string
  default     = "ap-south-1"
}

variable "name" {
  description = "Prefix for every resource name. Use a different value than your console-built copy so they don't collide."
  type        = string
  default     = "waste-watcher-iac"
}

variable "notification_email" {
  description = "Where the daily digest is sent. You must click the confirmation link AWS emails you."
  type        = string
}

variable "dashboard_token" {
  description = "Shared secret the dashboard sends to the API. Long and random."
  type        = string
  sensitive   = true
}

variable "allowed_origin" {
  description = "Website address allowed to call the API (CORS). Use * only while testing."
  type        = string
  default     = "http://127.0.0.1:5500"
}

variable "schedule_expression" {
  description = "When to scan, in EventBridge cron syntax."
  type        = string
  default     = "cron(0 9 * * ? *)"
}

variable "schedule_timezone" {
  type    = string
  default = "Asia/Kolkata"
}

variable "lambda_runtime" {
  description = "Python runtime for both functions. Change if AWS retires this one."
  type        = string
  default     = "python3.13"
}
