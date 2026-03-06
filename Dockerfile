# Use an official Python runtime as a parent image
FROM python:3.11

# Set the working directory in the container

# Copy the requirements file
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt

# Copy the application code
COPY . .

# Expose the port
EXPOSE 6780

# Run the command to start the application
CMD ["python", "main.py"]
