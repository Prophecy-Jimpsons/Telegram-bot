# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . .

# Install any necessary dependencies specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt



# Run the main.py script
CMD ["python", "main.py"]
