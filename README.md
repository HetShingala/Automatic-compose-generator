# Docker Compose Generator — MLOps Evaluation Task

## Project Structure

```
compose_generator/
├── app.py                    # Flask web app (entry point)
├── requirements.txt          # Flask dependency
├── generator/
│   ├── __init__.py
│   ├── composer.py           # Core generation logic
│   └── entrypoint.sh         # Entrypoint script for generated containers
├── templates/
│   └── index.html            # UI form
└── ml_pipeline/              # Sample ML project to containerize
    ├── train.py
    ├── evaluate.py
    ├── requirements.txt
    ├── data/
    │   └── dataset.csv
    ├── models/               # Empty — populated at runtime
    └── reports/              # Empty — populated at runtime
```

## Task

### Part 1 — Run the Generator App

```bash
cd compose_generator
pip install -r requirements.txt
python app.py
```

Visit http://localhost:5050 in your browser.

### Part 2 — Generate Docker files for the ML Pipeline

Use the form to configure and generate a `Dockerfile` + `docker-compose.yml` for `ml_pipeline/`.

Suggested form values:
- **Service name:** `ml-pipeline`
- **Base image:** `python:3.11-slim`
- **Port:** `8080`
- **Env vars:** `MODEL_PATH=/app/models/model.pkl`
- **Volumes:** `./models:/app/models` and `./reports:/app/reports`

### Part 3 — Get the pipeline running end-to-end

Place the generated files inside `ml_pipeline/`, then:

```bash
cd ml_pipeline
docker compose up --build
```

A successful run will produce:
- `ml_pipeline/models/model.pkl`
- `ml_pipeline/reports/report.json`

### Part 4 — Write-up

Write one paragraph per bug you found and fixed. For each:
- What was the symptom?
- How did you find it?
- What was the root cause?
- What did you fix and why?


## Part 5 - Add Model Versioning Layer 

- Use Mlflow to track multiple training runs and model versioning

## Part 6 - Add Observability Layer 

- Use Prometheus & Grafana for tracking model as well as inferencing metrics

## Part 7 - Hand Over

- Present the week's progress on the task interactively.

## Notes

- You may use AI tools freely.
- The write-up is your own work — explaining *why* a bug exists matters more than just fixing it.

## Stretch Goal

- Code Linting & Scanning
- Image Vulnerability Scanning
- One clicke OPS WebAPP encapsulating the entire task.