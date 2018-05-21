FROM python:3

WORKDIR /usr/src/app

COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "./beta_static_generator.py", "--notifications", "--save-s3", "--publish-stats", "--heartbeat"]
