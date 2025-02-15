# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "fastapi",
#     "uvicorn",
#     "requests",
#     "chromadb",
#     "black",
#     "openai",
#     "pillow",
#     "pydub",
#     "markdown2",
#     "beautifulsoup4",
#     "pandas",
#     "speechrecognition"
# ]
# system-dependencies = [
#     "nodejs",
#     "npm"
# ]
# npm-dependencies = [
#     "prettier@3.4.2"
# ]
# ///

from fastapi import FastAPI, HTTPException
import os
import subprocess
import sys
import json
import requests
import chromadb
import traceback
import time
import black
import re
import datetime
import sqlite3
import subprocess
import glob
from typing import Dict
import requests
import csv
from PIL import Image
from pydub import AudioSegment
import markdown2
import base64
from bs4 import BeautifulSoup
import uvicorn
import textwrap
import pandas
import speechrecognition

# Initialize FastAPI app
app = FastAPI()

# Initialize ChromaDB client
chroma_client = chromadb.PersistentClient(path="./chroma")
collection = chroma_client.get_or_create_collection(name="tasks")

# OpenAI API setup
OPENAI_API_KEY = os.environ.get("AIPROXY_TOKEN")
API_URL = os.environ.get("API_URL", "https://aiproxy.sanand.workers.dev/openai/v1/chat/completions")

BUILT_IN_MODULES = {"datetime", "sys", "os", "json", "traceback", "uv"}  # Common built-in modules to exclude

response_format = {
    "type": "json_schema",
    "json_schema": {
        "name": "task_runner",
        "schema": {
            "type": "object",
            "required": ["python_dependencies", "python_code"],
            "properties": {
                "python_code": {
                    "type": "string",
                    "description": "Python code to perform the task. and run the subprocess using uv run"
                },
                "python_dependencies": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "module": {
                                "type": "string",
                                "description": "Name of Python module"
                            }
                        },
                        "required": ["module"],
                        "additionalProperties": False
                    }
                }
            }
        }
    }
}

# Function to sanitize and execute Python code with LLM-driven correction
def sanitize_and_execute_code(python_code, dependencies, filename):
    try:
        # Remove unnecessary spaces/tabs
        #python_code = "\n".join([line.lstrip() for line in python_code.split("\n")])
        python_code = textwrap.dedent(python_code)

        # Remove built-in modules from dependencies
        filtered_dependencies = [dep for dep in dependencies if dep["module"] not in BUILT_IN_MODULES]

        # Ensure correct formatting
        try:
            formatted_code = black.format_str(python_code, mode=black.FileMode())
        except black.InvalidInput:
            formatted_code = python_code  # Use raw code if formatting fails
        dependency_list = ",\n".join(f'#    "{dep["module"]}"' for dep in filtered_dependencies)

# Ensure properly formatted inline metadata
        inline_metadata_script = f""" 
# ///script
# requires-python = ">=3.11"
# dependencies = [
{dependency_list}
# ]
# ///
"""
        with open(filename, "w") as f:
            f.write(inline_metadata_script + "\n")
            f.write(formatted_code)

        # Execute file with up to 3 self-correcting retries
        for attempt in range(3):
            try:
                result = subprocess.run(
        ["uv", "run", filename],  # Runs the script using uv
        capture_output=True,
        text=True,
        timeout=30
    )
                if result.returncode == 0:
                    return result.stdout.strip()
                else:
                    error_message = result.stderr.strip()
                    print(f"Attempt {attempt + 1}: Execution failed with error: {error_message}")

                    # Send error to LLM for correction
                    gpt_response = query_gpt(f"Fix the following execution error: {error_message}")
                    try:
                        response_content = json.loads(gpt_response["choices"][0]["message"]["content"])
                        python_code = response_content["python_code"].strip()

                        # Rewrite the file with corrected code
                        with open(filename, "w") as f:
                            f.write(inline_metadata_script + "\n")
                            f.write(python_code)
                    except Exception:
                        continue  # If LLM response is invalid, move to next attempt
            except Exception as e:
                print(f"Attempt {attempt + 1}: Exception occurred: {str(e)}")
                continue

        return "Execution failed after 3 attempts."
    except Exception:
        return f"Execution error: {traceback.format_exc()}"

import requests
import json

def classify_task(task_description):
    """
    Classifies the task description to determine which execution strategy to use.
    The LLM will analyze the description and return the most appropriate category.
    """
    classification_prompt = f"""
    You are an LLM automation agent. Given the following task description, classify it into one of these categories:
    
    - "run_python_script" → If the task involves extracting a URL and executing a Python script with parameters.
    - "format_markdown" → If the task involves modifying markdown files.
    - "date_parsing" → If the task involves handling date formats and parsing days of the week.
    - "sort_contacts" → If the task involves sorting JSON-based contacts.
    - "gold_ticket_sales" → If the task involves querying a sales database for "Gold" ticket revenue.
    - "extract_credit_card" → If the task involves extracting credit card numbers from images or files.
    - "markdown_indexing" → If the task involves scanning `.md` files for H1 titles and generating an index.
    - "similar_comments" → If the task involves identifying similar comments using embeddings.
    - "email_processing" → If the task involves extracting structured data from email messages.
    
    ## **Business Tasks**
    - "fetch_api" → If the task requires fetching data from an API and saving it.
    - "git_clone_commit" → If the task involves cloning a git repository and making a commit.
    - "run_sql_query" → If the task involves executing SQL queries on an SQLite or DuckDB database.
    - "web_scraping" → If the task requires extracting data from a webpage (scraping).
    - "compress_image" → If the task involves compressing or resizing an image.
    - "transcribe_audio" → If the task requires transcribing audio from an MP3 file to text.
    - "markdown_to_html" → If the task involves converting Markdown to HTML.
    - "csv_filter" → If the task requires filtering a CSV file and returning JSON data.

    ## **Security Constraints**
    - **B1: No file outside `/data/` should be accessed or written.**
    - **B2: No file deletion is allowed anywhere on the system.**
    
    Task Description:
    {task_description}
    
    Respond with only the category name.
    """

    response = requests.post(
        API_URL,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {OPENAI_API_KEY}"},
        json={
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "Classify the given task."},
                {"role": "user", "content": classification_prompt}
            ]
        }
    )

    classification = response.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    print(f"Task classification: {classification}")
    return classification


def query_gpt(task_description: str):
    """
    Classifies the task and generates the corresponding Python code.
    The LLM will infer input/output file paths dynamically from the task description.
    """
    task_category = classify_task(task_description)

    # Define the primary execution prompt
    primary_prompt = f"""
    ## LLM Automation Agent - Intelligent Task Execution  

    ### **🔹 Context**
    You are an **LLM-based automation agent** that executes plain-English tasks programmatically.  
    Your objective is to:  
    1. **Identify the task category from the description.**  
    2. **Automatically detect input and output file paths.**  
    3. **Generate structured, error-free Python code** that correctly processes these files.  
    4. **Ensure execution is efficient and secure.**  
    5. **In general extract the input and output folder paths from the task description**
    6. ** File names should strictly be used as per the task description**  

    ---
    ### **🚀 Execution Strategy**
    - The LLM **must infer the correct input/output file paths** from the task description.
    - If the task involves **reading a file**, determine the likely filename and ensure it is used properly.
    - If the task involves **writing to a file**, define a meaningful output file.
    - Ensure valid indentation and syntax to avoid runtime failures.
    - The script should **not delete or modify files outside `/data/`**.
    - **Automatically handle missing dependencies** by listing them under `"dependencies"`.
    - Ensure the script **does not exceed 20 seconds** and includes **retry logic**.
    - Validate the generated script using `black` before execution.

    ---
    ## ** Security & Compliance Rules**
    - **B1: Data outside `/data/` must NEVER be accessed or exfiltrated.**
    - **B2: No file should be deleted anywhere on the system.**
    - **B3-B10: Implement execution strategies based on the task category.**
    """

    # **Task-Specific Execution Strategies - LLM Infers File Paths**
    task_specific_prompt = {
        "run_python_script": f"""
        Task Description:
        {task_description}

        - Download the Python script from the given URL.
        - Save it locally.
        - Run the script using `uv run` with the extracted email argument.
         Sample Execution:
        ```python
        subprocess.run(["uv", "run", "script.py", "email"])
        ```
        """,
        "format_markdown": f"""
        Task Description:
        {task_description}

         - Use npx.cmd instead of npx to support Windows-based execution.
         - Wrap subprocess calls in a try-except block to handle errors gracefully.
         - Raise proper HTTP exceptions for FileNotFoundError and subprocess.CalledProcessError.
         - Return a success message when formatting is completed.
        """,
        "date_parsing": f"""
        Task Description:
        {task_description}

        - Count occurrences of Wednesdays in a file.
        - Handle multiple date formats.
         date formats:
        - "%Y-%m-%d"
        - "%d-%b-%Y"
        - "%b %d, %Y"
        - "%Y/%m/%d %H:%M:%S"

        """,
        "sort_contacts": f"""
        Task Description:
        {task_description}

        - Sort contacts in a JSON file by last name and first name.
        and write the sorted result to output file
        """,
        "markdown_indexing": f"""
        Task Description:
        {task_description}

        - Extract `H1` titles from Markdown files.
        - Generate an index mapping filenames to titles.
        """,
        "gold_ticket_sales": f"""
        Task Description:
        {task_description}

        Query `ticket-sales.db` from `input_file` to compute total revenue from "Gold" ticket sales.
        Write the computed revenue to `output_file.
        """,
       "fetch_api": f"""
Task Description:
{task_description}

- Fetch data from an API endpoint using `requests`.
- Handle authentication and error handling for failed requests.
- Ensure the response is correctly formatted as JSON before saving.
- Save the API response to the output file.
""",

"git_clone_commit": f"""
Task Description:
{task_description}

- Clone the Git repository using `subprocess`.
- Ensure the repository exists and is accessible.
- Modify or add a new file to the repository.
- Use `git` commands to commit and push changes.
- Verify the commit before finalizing the process.
""",

"run_sql_query": f"""
Task Description:
{task_description}

- Connect to the SQLite or DuckDB database.
- Execute the specified SQL query using `sqlite3` or `duckdb`.
- Fetch the query results and structure them in JSON format.
- Save the query output to the output file.
- Handle database connection errors gracefully.
""",

"web_scraping": f"""
Task Description:
{task_description}

- Extract webpage content using `beautifulsoup4`.
- Parse and filter the relevant text or data elements.
- Handle page navigation and pagination if required.
- Save the extracted content in structured format (JSON or TXT).
- Ensure error handling for inaccessible pages or missing elements.
""",

"compress_image": f"""
Task Description:
{task_description}

- Read the input image file using `pillow`.
- Resize or compress the image while maintaining aspect ratio.
- Adjust quality settings to optimize file size.
- Save the compressed image in the output file.
- Ensure image format and metadata remain intact.
""",

"transcribe_audio": f"""
Task Description:
{task_description}

- Convert an MP3 audio file to text using `pydub` and `speechrecognition`.
- Preprocess the audio by converting it to WAV format.
- Use an ASR model (Google Speech API or another) to generate a transcript.
- Save the transcribed text to the output file.
- Handle errors for corrupted or unsupported audio files.
""",

"markdown_to_html": f"""
Task Description:
{task_description}

- Convert the input Markdown file to HTML using `markdown2`.
- Preserve the original structure, links, and formatting.
- Ensure special characters and embedded content are rendered properly.
- Save the converted HTML content to the output file.
""",

"csv_filter": f"""
Task Description:
{task_description}

- Read the CSV file using `pandas`.
- Filter rows based on the specified conditions (e.g., column values).
- Save the filtered output in JSON format.
- Handle CSV parsing errors and ensure data consistency.
""",
      
        "extract_credit_card": f"""
        Task Description:
{task_description}

- Read the image file input_file.
- Convert the image into **base64** format and encode it as a **data URI**.
- Send the encoded image to the **AI Proxy API** for text extraction.
- Extract only the **credit card number** from the response.
-Doublec check before saving the card number to output_file.
- Remove all spaces before saving the card number to output_file.""",

        "similar_comments": f"""
Task Description:
{task_description}
- Read comments from the file
- Prompt an external LLM (GPT-4o-mini) via API to identify the most similar pair
- Write the results to the output file
- Handle API errors gracefully
""",
    }.get(task_category, None)

    # **Fallback Strategy for Unrecognized Tasks**
    if not task_specific_prompt:
        task_specific_prompt = f"""
        The task description was **unrecognized**. Please generate an appropriate Python script.
        
        Task Description:
        {task_description}

        - **Identify the input and output file paths dynamically.**
        - **Handle file reading/writing safely.**
        - **Ensure valid error handling.**

        Expected output format:
        ```json
        {{
          "python_code": "generated python code",
          "python_dependencies": []
        }}
        ```
        """

    # **Send request to LLM with classified prompt**
    response = requests.post(
        API_URL,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {OPENAI_API_KEY}"},
        json={
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": primary_prompt},
                {"role": "user", "content": task_specific_prompt}
            ],
            "response_format": response_format
        }
    )

    return response.json()


# Function to query the LLM for code generation

    python_code = ""
    dependencies = []

# Endpoint to run a task
# POST /run?task=<task description>
@app.post("/run")
def run_task(task: str):
    """
    Executes a plain-English task by:
    - Classifying the task
    - Generating Python code via LLM
    - Running the generated script using `uv run`
    - Handling errors appropriately
    """
    python_code = ""
    dependencies = []

    try:
        # Query the LLM to classify and generate Python code
        gpt_response = query_gpt(task)

        # Parse the LLM response
        response_content = json.loads(gpt_response["choices"][0]["message"]["content"])
        python_code = response_content.get("python_code", "").strip()
        dependencies = response_content.get("python_dependencies", [])

        if not python_code:
            raise HTTPException(status_code=400, detail="No valid Python code generated.")

        # Create a filename for execution
        filename = f"generated_task_{int(time.time())}.py"

        # Execute the generated Python script
        output = sanitize_and_execute_code(python_code, dependencies, filename)

        return {"status": "success", "task": task, "generated_code": python_code, "output": output}

    except HTTPException as e:
        # Raise HTTPException directly for user-related errors (400)
        raise e

    except Exception as e:
        # Handle unexpected agent errors (500)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@app.get("/read")
def read_file(path: str):
    """
    Reads the content of a specified file.
    - Returns 200 OK if successful.
    - Returns 404 Not Found if the file does not exist.
    """

    try:
        # Ensure the file is inside the /data/ directory
        if not path.startswith("/data/"):
            raise HTTPException(status_code=400, detail="Access restricted to /data/ directory.")

        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="File not found.")

        # Read file content
        with open(path, "r", encoding="utf-8") as file:
            content = file.read()

        return {"status": "success", "file": path, "content": content}

    except HTTPException as e:
        # Raise HTTP exceptions for known issues
        raise e

    except Exception as e:
        # Handle unexpected agent errors (500)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")


if __name__ == "__main__":
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
