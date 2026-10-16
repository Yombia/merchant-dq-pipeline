# Small, separate image for the dashboard: keeps Streamlit's dependencies out of Airflow's.
FROM python:3.12-slim
RUN pip install --no-cache-dir streamlit==1.66.0 altair==6.3.0 pandas psycopg2-binary
WORKDIR /opt/project
EXPOSE 8501
CMD ["streamlit", "run", "dashboard/app.py", "--server.port=8501", "--server.address=0.0.0.0", \
     "--server.headless=true", "--browser.gatherUsageStats=false"]
