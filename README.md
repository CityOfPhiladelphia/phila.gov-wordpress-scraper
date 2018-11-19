# phila.gov-wordpress-scraper

Python CLI app that scrapes the phila.gov wordpress site to generate static HTML pages.
Requires a [WordPress API endpoint](https://github.com/CityOfPhiladelphia/phila.gov/blob/master/wp/wp-content/plugins/phila.gov-customization/public/class-phila-last-updated-controller.php) listing all WordPress-generated pages.

## Local development

Requirements:

* Python 3
* Docker
* A tool to create isolated Python environments like `virtualenv` or `pipenv`. This guide will use `pipenv`.

### Setup

1.  After installing [docker](https://www.docker.com/get-started) on your machine, cd into directory and run `docker build .` to create the image.
2. `pipenv shell` to activate the shell.
3. `pipenv install` to install project dependencies.
4. `. env.sh` to source your environment variables.
5. `python phila_site_scraper.py` to run the scraper locally.

## Deploying

1. Find `phila-gov-wordpress-scraper` in AWS ECR Repositories.
2. Follow the `View Push Commands` instructions through step 3.
3. `docker tag phila-gov-wordpress-scraper:latest 676612114792.dkr.ecr.us-east-1.amazonaws.com/phila-gov-wordpress-scraper:GITCOMMITSHA` - Create and tag a local version of the image. Replace `GITCOMMITSHA` in the above example with the commit sha of the latest build. This essentally versions the image, instead of replacing the image tagged as `LATEST` (as AWS instructs). 
4. `docker push 676612114792.dkr.ecr.us-east-1.amazonaws.com/phila-gov-wordpress-scraper:GITCOMMITSHA` - Create the image in the ECR Repository. Remember to replace `GITCOMMITSHA` with the SHA in the previous step. 
5. Login to [Terraform Enterprise](https://app.terraform.io) and update the `wordpress_scraper_image` variable with the new scrapper tag.

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
