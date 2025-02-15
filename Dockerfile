FROM python:3.12

# Set environment variables inside the Docker container
ENV user_email="23f1001611@ds.study.iitm.ac.in"

# Install required system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates python3-pip

# Upgrade pip globally
RUN pip3 install --upgrade pip
RUN pip install SpeechRecognition
# Download and install uv
ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh

# Ensure uv is in the correct path
RUN echo "Checking if uv is installed..." && ls -lah /root/.local/bin/

# Manually add uv to PATH
ENV PATH="/root/.local/bin:$PATH"

# Verify uv installation
RUN which uv && uv --version

WORKDIR /app
RUN mkdir -p /data
COPY app.py /app

CMD ["uv", "run", "app.py"]
