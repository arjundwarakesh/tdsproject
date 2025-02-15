FROM python:3.12

# Set environment variables inside the Docker container
ENV user_email="23f1001611@ds.study.iitm.ac.in"
ENV AIPROXY_TOKEN="eyJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6IjIzZjEwMDE2MTFAZHMuc3R1ZHkuaWl0bS5hYy5pbiJ9.SInDAwejjF3oWlCM_kwnNGpldkE4b8ykgafJuJv3I4Q"

# Install required system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates python3-pip

# Upgrade pip globally
RUN pip3 install --upgrade pip

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
