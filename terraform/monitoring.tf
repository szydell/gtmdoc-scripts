# ---------------------------------------------------------------------------
# Internet Monitor — monitorowanie dostępności i latencji CloudFront
# ---------------------------------------------------------------------------

resource "aws_internetmonitor_monitor" "site" {
  monitor_name = "${var.bucket_name}-monitor"

  resources = [
    aws_cloudfront_distribution.site.arn,
  ]

  # 100% ruchu monitorowane; ogranicz max city-networks żeby kontrolować koszty
  traffic_percentage_to_monitor = 100
  max_city_networks_to_monitor  = 500

  status = "ACTIVE"
}
