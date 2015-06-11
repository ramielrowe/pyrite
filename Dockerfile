FROM python:2.7

EXPOSE 5000

WORKDIR /pyrite/

ADD requirements.txt /pyrite/requirements.txt
RUN pip install -r requirements.txt
RUN pip install gunicorn

ADD pyrite.py /pyrite/pyrite.py
ADD pyrite.yaml /pyrite/pyrite.yaml

VOLUME /keys
ENV MAKE_SWARM_DIR=/keys

CMD ["gunicorn", \
     "-b", "0.0.0.0:5000", \
     "-w", "4", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--log-file", "-", \
     "pyrite:APP"]
