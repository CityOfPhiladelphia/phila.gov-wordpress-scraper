# phila.gov-wordpress-scraper

Python CLI app that scrapes the phila.gov wordpress site to generate static HTML pages.
Requires a [WordPress API endpoint](https://github.com/CityOfPhiladelphia/phila.gov/blob/master/wp/wp-content/plugins/phila.gov-customization/public/class-phila-last-updated-controller.php) listing all WordPress-generated pages.

## Usage

Using local disk

```sh
python phila_site_scraper.py
```

Using S3

```sh
python phila_site_scraper.py --save-s3
```

Production

```sh
python phila_site_scraper.py --save-s3 --invalidate-cloudfront --notifications --publish-stats --heartbeat
```
Help

```sh
> python phila_site_scraper.py --help
Usage: phila_site_scraper.py [OPTIONS]

Options:
  --save-s3                       Save site to S3 bucket.
  --invalidate-cloudfront         Invalidates CloudFront paths that are
                                  updated.
  --logging-config TEXT           Python logging config file in YAML format.
  --num-worker-threads INTEGER    Number of workers.
  --notifications / --no-notifications
                                  Enable Slack/email error notifications.
  --publish-stats / --no-publish-stats
                                  Publish stats to Cloudwatch
  --heartbeat / --no-heartbeat    Cloudwatch hearbeat
  --help                          Show this message and exit.
```

## Environment Variables

| Variable | Example | Description |
| -------- | ------- | ----------- |
| `SCRAPER_SLACK_URL` | https://hooks.slack.com/services/... | A Slack webhook URL for an alerts channel. |
| `SCRAPER_HOSTNAMES_TO_FIND` | "admin.phila.website\|beta.phila.gov" | The hostnames to find for replacement in the scraped page content. |
| `SCRAPER_HOSTNAME_REPLACE` | www.phila.website | The new website host. |
| `SCRAPER_HOST_FOR_URLS_AND_PAGES` | Wordpress server host to scrape pages from |
| `SCRAPER_S3_BUCKET` | www.phila.website | S3 bucket to store scrapped. |
| `SCRAPER_CLOUDFRONT_DISTRIBUTION` | EAURQRDQU47EO | For Cloudfront cache invalidation, the distrbution in front of the S3 bucket. |
| `SCRAPER_CLOUDFRONT_MAX_INVALIDATIONS` | 50 | Maximum number of invalidations to perform per run. |
| `SCRAPER_CLOUDFRONT_CLOUDWATCH_NAMESPACE` | 'test-cloudfront' | A namespace for the scraper cloudfront metrics |
