# Databricks notebook source
# Trivial serverless job body — exists only to generate JOBS-category rows in
# system.billing.usage (with Service_ID custom tags from the job definition).
# Imported to /Shared/aiprice_job_nb in the dbx-aiprice-mw929 test workspace.
print(spark.range(10_000_000).selectExpr("sum(id)").collect()[0][0])
