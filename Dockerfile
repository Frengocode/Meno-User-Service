FROM python:3.12

COPY requirements.txt requirements.txt

RUN pip3 install -r requirements.txt

COPY . .

RUN chmod +x run.sh

CMD ["./run.sh"]
