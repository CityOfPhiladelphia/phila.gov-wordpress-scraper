FROM python:3

WORKDIR /usr/src/app

COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "./phila_site_scraper.py", "--notifications", "--save-s3", "--invalidate-cloudfront", "--publish-stats", "--heartbeat"]