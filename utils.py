from dash import dcc, html
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from glob import glob
from httpx import ConnectTimeout
from pathlib import Path
from starlette.middleware.wsgi import WSGIMiddleware
from tenacity import retry, retry_if_exception_type, stop_after_attempt
from tqdm.auto import tqdm
from typing import Optional
import dash
import dash_bootstrap_components as dbc
import json
import openml
import os
import pandas as pd
import plotly.express as px
import sqlite3


class OpenMLTaskHandler:

    def get_target_col_type(self, dataset, target_col_name):
        try:
            if dataset.features:
                return next(
                    (
                        feature.data_type
                        for feature in dataset.features.values()
                        if feature.name == target_col_name
                    ),
                    None,
                )
        except Exception as e:
            print(f"Error getting target column type: {e}")
            return None

    def try_create_task(self, dataset_id):
        try:
            dataset = openml.datasets.get_dataset(dataset_id)
            target_col_name = dataset.default_target_attribute
            target_col_type = self.get_target_col_type(dataset, target_col_name)

            if target_col_type:
                if target_col_type in ["nominal", "string", "categorical"]:
                    evaluation_measure = "predictive_accuracy"
                    task_type = openml.tasks.TaskType.SUPERVISED_CLASSIFICATION
                elif target_col_type == "numeric":
                    evaluation_measure = "mean_absolute_error"
                    task_type = openml.tasks.TaskType.SUPERVISED_REGRESSION
                else:
                    return None

                task = openml.tasks.create_task(
                    dataset_id=dataset_id,
                    task_type=task_type,
                    target_name=target_col_name,
                    evaluation_measure=evaluation_measure,
                    estimation_procedure_id=1,
                )

                # if self.check_if_api_key_is_valid():
                task.publish()
                print(f"Task created: {task}, task_id: {task.task_id}")
                return task.task_id
                # else:
                # return None
            else:
                return None

        except Exception as e:
            print(f"Error creating task: {e}")
            return None

    def get_openml_task_id_from_string(self, string):
        try:
            return int(string.split("/")[-1])
        except:
            return None

    def get_dataset_id_from_task_id(self, string):
        task_id = self.get_openml_task_id_from_string(string=string)
        if task_id is not None:
            try:
                return openml.tasks.get_task(
                    task_id=task_id,
                    download_data=False,
                    download_qualities=False,
                    download_splits=False,
                    download_features_meta_data=False,
                ).dataset_id
            except:
                return None
        else:
            return None


class SQLHandler:
    def __init__(self, db_path):
        self.db_path = db_path
        self.initialize_database()

    def initialize_database(self):
        """Set up the SQLite database if it doesn't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                dataset_id INTEGER,
                task_id INTEGER,
                framework TEXT,
                PRIMARY KEY (dataset_id, task_id, framework)
            )
        """
        )
        conn.commit()
        conn.close()

    def task_already_run(self, dataset_id, task_id, framework):
        """Check if a task has already been run for a given dataset, task, and framework."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 1 FROM runs WHERE dataset_id = ? AND task_id = ? AND framework = ?
        """,
            (dataset_id, task_id, framework),
        )
        result = cursor.fetchone()
        conn.close()
        return result is not None

    def save_run(self, dataset_id, task_id, framework):
        """Save a run to the database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO runs (dataset_id, task_id, framework) VALUES (?, ?, ?)
        """,
            (dataset_id, task_id, framework),
        )
        conn.commit()
        conn.close()
