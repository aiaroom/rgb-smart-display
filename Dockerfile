FROM python:3.12-alpine

WORKDIR /app

RUN apk add --no-cache gcc musl-dev libffi-dev postgresql-client postgresql-dev

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod 777 docker-entrypoint.sh

ENTRYPOINT ["./docker-entrypoint.sh"]

CMD ["app"]