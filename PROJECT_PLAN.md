# Mini Project Plan: Prefect + Supabase Job Market Pipeline

## Objective
Build a simple data engineering project that demonstrates orchestration with Prefect, data storage and SQL analytics with Supabase, and a lightweight analytics dashboard web app. The project should showcase an ELT pipeline and medallion architecture (bronze/silver/gold).

The final output should include:
- A working Prefect pipeline
- Data stored and transformed in Supabase
- Analytics tables
- A simple web dashboard showing the analytics

If any requirement or design decision is unclear, ASK THE USER before proceeding instead of making assumptions.

---

# Architecture Overview

Data Source (Public Job API)  
→ Prefect Pipeline (Extract + Transform)  
→ Supabase PostgreSQL (Bronze / Silver / Gold)  
→ Analytics Queries  
→ Simple Web Dashboard

---

# Technologies

Orchestration:
- Prefect

Database / Backend:
- Supabase (PostgreSQL)

Dashboard:
- Simple web app to be built using Lovable

Language:
- Python

---

# Data Source

Use a public job listing API.

Possible APIs:
- RemoteOK
- Arbeitnow
- Any public job API returning JSON

If unsure which API to use, ask the user.

---

# Data Architecture

Use medallion architecture.

## Bronze Layer

Table: `jobs_raw`

Purpose:
Store raw API responses.

Suggested columns:
- id
- title
- company
- location
- tags
- salary
- posted_date
- raw_json
- ingested_at

---

## Silver Layer

Table: `jobs_clean`

Purpose:
Clean and normalize job data.

Suggested fields:
- job_id
- title
- company
- country
- salary_min
- salary_max
- tech_stack
- posted_date

Transformations:
- parse salary
- normalize tech stack
- extract country
- remove duplicates

---

## Gold Layer

Table: `job_market_summary`

Purpose:
Aggregated analytics table.

Suggested fields:
- date
- job_count
- avg_salary
- remote_ratio
- top_tech_stack

---

# Prefect Pipeline

Create a Prefect flow that orchestrates the pipeline.

## Tasks

1. extract_jobs
Fetch job listings from the API.

2. load_raw_jobs
Insert records into `jobs_raw`.

3. transform_jobs
Transform raw data into cleaned format.

4. load_clean_jobs
Insert into `jobs_clean`.

5. build_analytics_table
Generate aggregated analytics for `job_market_summary`.

---

# Pipeline Features

Include the following:

Retries for API calls.

Example:
- retries: 3
- retry delay: 60 seconds

Logging:
Log number of records extracted and inserted.

Example logs:
- jobs fetched
- rows inserted
- transformation results

Scheduling:
Run pipeline daily.

---

# Data Quality Checks

Implement simple checks:

- row count > 0
- no null company values
- no duplicate job ids

Log warnings if checks fail.

---

# Repository Structure
prefect-supabase-job-pipeline/

flows/
job_pipeline.py

tasks/
extract_jobs.py
load_supabase.py
transform_jobs.py

deployment/
deploy.py

sql/
bronze_schema.sql
silver_schema.sql
gold_tables.sql

config/
settings.py

dashboard/

README.md

---

# Web Analytics Dashboard

Create a simple web dashboard that reads analytics data from Supabase.

This dashboard will be generated using Lovable via prompting.

Purpose of dashboard:
Show job market insights from the Gold layer.

Suggested visualizations:

1. Total Jobs
2. Average Salary
3. Remote vs Onsite Ratio
4. Top Technologies
5. Jobs Posted Over Time

Dashboard requirements:
- Clean and minimal UI
- Use Supabase queries or API to fetch data
- Show charts or summary cards

If the agent is unsure about:
- chart types
- layout
- colors
- UI structure

ASK THE USER before implementing.

---

# Portfolio Description

Project demonstrates:

- Data ingestion from public APIs
- Orchestration with Prefect
- Medallion data architecture
- SQL transformations
- Data quality checks
- Automated pipelines
- Analytics dashboard powered by Supabase

---

# Success Criteria

The project is complete when:

1. Prefect pipeline runs successfully.
2. Data is stored in Supabase bronze/silver/gold tables.
3. Analytics tables populate correctly.
4. Pipeline can run on schedule.
5. Web dashboard displays analytics from Supabase.