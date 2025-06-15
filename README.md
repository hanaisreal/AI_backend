# AI Awareness Project Backend

A FastAPI-based backend service that handles user data processing, AI integrations, and content generation for the AI Awareness Project.

## 🏗️ Project Structure

```
backend/
├── main.py            # FastAPI application entry point
├── crud.py            # Database CRUD operations
├── models.py          # SQLAlchemy database models
├── schemas.py         # Pydantic data validation schemas
├── database.py        # Database connection and session setup
└── requirements.txt   # Python dependencies
```

## 🚀 API Endpoints

### User Management
- `POST /api/user-info`
  - Save user information (name, age, gender) to a SQLite database.
  - Returns: user object with a unique ID.

- `GET /api/users/{user_id}`
  - Retrieve a user's information from the database.

### Quiz Management
- `POST /api/quiz-answers`
  - Save a user's quiz answers for a specific module to the database.
  - Required fields: user_id, module, answers.

### Media Processing & Content Generation
- `POST /api/user-image`
  - Uploads user photo to an **S3 bucket**.
  - Returns: s3_url.
- `POST /api/generate-talking-photo`
  - Creates animated talking photo using Akool API.
  - Stores the generated video in an **S3 bucket**.
  - Returns: video_url.
- `POST /api/generate-faceswap-image`
  - Performs face swap on images, stores result in **S3**.

## 🛠️ Technology Stack

- Python 3.x
- FastAPI & Uvicorn
- **SQLite** (for user and quiz data)
- **SQLAlchemy** (for database ORM)
- **Amazon S3** (for image and video storage)
- OpenAI API
- ElevenLabs API
- Akool API

## 🚀 Getting Started

1. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file with required environment variables:
   ```
   # AI Service Keys
   OPENAI_API_KEY=your_openai_api_key
   ELEVENLABS_API_KEY=your_elevenlabs_api_key
   AKOOL_API_KEY=your_akool_api_key

   # AWS S3 Credentials for media storage
   AWS_ACCESS_KEY_ID=your_aws_access_key
   AWS_SECRET_ACCESS_KEY=your_aws_secret_key
   S3_BUCKET_NAME=your_s3_bucket_name
   ```
   *The SQLite database will be created as `test.db` in the backend directory.*

4. Start the server:
   ```bash
   uvicorn main:app --reload
   ```

## 📝 API Documentation

Once the server is running, API documentation is available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc` 