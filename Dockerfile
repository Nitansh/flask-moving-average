FROM python:3.8.3
RUN apt-get install ca-certificates

# switch working directory
WORKDIR /app

# copy the requirements file into the image
COPY ./requirements.txt /app/requirements.txt
# install the dependencies and packages in the requirements file
RUN pip3 install --trusted-host=pypi.org --trusted-host=files.pythonhosted.org --user pip-system-certs -r requirements.txt

# copy every content from the local file to the image
COPY . /app

EXPOSE 5000
ENV PORT 5000

HEALTHCHECK --timeout=3s --retries=2 CMD curl --fail http://localhost:5000/healthcheck || exit 1 

# configure the container to run in an executed manner
ENTRYPOINT [ "python3" ]

CMD ["app.py" ]