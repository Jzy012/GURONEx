<h1 style="font-size: 50px;">LINANG</h1>
<h3 >Linking Information Network for Administration and Narrative Gathering</h3>


---

## 📌 Overview  
**LINANG** is a **web-based Human Resources Information System** designed to streamline academic administrative processes.  
It provides **automated attendance tracking**, **document management**, and **faculty and applicant management** within the system.

The primary goal is to **improve efficiency and transparency** by automating manual workflows, reducing paperwork, and enabling centralized access to information.

---

## ✨ Key Features  
✅ **Automated Attendance**  
- RFID-based time-in/out system using **ESP32** for seamless Wi-Fi backend connectivity.

✅ **Faculty & Admin Dashboards**  
- Role-based access control with intuitive interfaces.

✅ **Document Management**  
- Secure Google Drive integration for faculty document uploads and centralized storage.

✅ **Applicant Management**  
- Simplified application process and admin approval workflow.

✅ **Announcements & Notifications**  
- System-wide announcements.

✅ **Optional Two-Factor Authentication (2FA)**  
- Email OTP for added account security.

✅ **Deliverables Tracking (for Faculty Clearance)**  
- Semester-based deliverables with deadlines, upload status, and remarks.

---

## 🛠 Tech Stack  
- **Backend:** Django (Python)  
- **Frontend:** Django Templates & Tailwind CSS  
- **Database:** PostgreSQL   
- **Cloud Storage:** Google Drive API  
- **RFID Integration:** ESP32 with RFID module (RC522)  
- **Authentication:** Django Auth Features with optional 2FA  

---



## 📂 Project Structure  
```bash
FEMS/
 ┣ adminhub/            # Admin dashboard & management features
 ┣ applicant/           # Applicant module (submission & approval flow)
 ┣ base/                # Core Django app (models, forms, utils, auth)
 ┣ faculty/             # Faculty dashboard & features
 ┣ FEMS/                # Project settings, urls, wsgi/asgi
 ┣ gdrive_credentials/  # Google Drive credentials (gitignored)
 ┣ node_modules/        # Dependencies for TailwindCSS (npm)
 ┣ rfid/                # RFID attendance module (ESP32 integration)
 ┣ services/            # External services integration (e.g., Google Drive API)
 ┣ static/              # Static files (CSS, JS, images)
 ┣ templates/           # HTML templates
 ┣ venv/                # Python virtual environment (gitignored)
 ┣ .env                 # Environment variables (gitignored)
 ┣ .gitignore           # Git ignore rules
 ┣ manage.py            # Django management script
 ┣ package.json         # Node.js dependencies
 ┣ package-lock.json    # Node.js lock file
 ┣ requirements.txt     # Python dependencies
 ┣ tailwind.config.js   # TailwindCSS configuration
 ┗ README.md            # Project documentation
```

---

## 🔑 Environment Variables  

Make sure to configure the following environment variables in your `.env` file:  

- `DEBUG` → `True` or `False` depending on development/production  
- `SECRET_KEY` → Your Django secret key  
- `DB_NAME` → Your database name  
- `DB_USER` → Your database user  
- `DB_PASSWORD` → Your database password  
- `DB_HOST` → Usually `localhost`  
- `DB_PORT` → Default is `5432` for PostgreSQL  
- `EMAIL_HOST_USER` → Your email address (used for sending OTPs, notifications, etc.)  
- `EMAIL_HOST_PASSWORD` → Your email app password  
- `GOOGLE_SERVICE_ACCOUNT_FILE` → Path to your Google service account JSON file (e.g., `gdrive_credentials/fems-gdrive-integration-key.json`)  
- `GOOGLE_CLIENT_SECRET_FILE` → Path to your Google OAuth client secret JSON file (e.g., `gdrive_credentials/client_secret.json`)  
- `GOOGLE_OAUTH2_REDIRECT_URI` → Redirect URI for Google OAuth (e.g., `http://localhost:8000/oauth2callback`)  
- `FERNET_KEY` → Your generated Fernet encryption key  


---

## 📜 License & Copyright

This project is developed as part of a Capstone Study and is intended for academic purposes only.

© 2025 LINANG Capstone Team. All Rights Reserved.

You are free to view, reference, and learn from the source code.
However, redistribution, reproduction, or commercial use of this project without prior permission from the authors is strictly prohibited.

