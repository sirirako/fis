import logging
import os
import psycopg2
import config
import repository
from flask import Flask, jsonify

# OTLP tracing
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource, get_aggregated_resources

# Exporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Propagation
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.aws import AwsXRayPropagator

# AWS X-Ray ID generator
from opentelemetry.sdk.extension.aws.trace import AwsXRayIdGenerator

# Resource detector
from opentelemetry.sdk.extension.aws.resource.eks import AwsEksResourceDetector

# Instrumentation
from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from opentelemetry.instrumentation.flask import FlaskInstrumentor

# OLTP Metrics
from opentelemetry import metrics
from opentelemetry.metrics import Observation
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.sdk.metrics import MeterProvider

# Flask exporter
from prometheus_flask_exporter import PrometheusMetrics

# Instrumentation
BotocoreInstrumentor().instrument()
Psycopg2Instrumentor().instrument()

# Setup flask app
app = Flask(__name__)
FlaskInstrumentor().instrument_app(app)

logging.basicConfig(level=os.getenv('LOG_LEVEL', 20), format='%(message)s')
logger = logging.getLogger()
cfg = config.fetch_config()
conn_params = config.get_rds_connection_parameters(cfg['rds_secret_arn'], cfg['region'])
db = psycopg2.connect(**conn_params)

# Setup AWS X-Ray propagator
set_global_textmap(AwsXRayPropagator())

# Setup AWS EKS resource detector
resource = get_aggregated_resources(
    [
        AwsEksResourceDetector(),
    ]
)

# Setup tracer provider with the X-Ray ID generator
tracer_provider = TracerProvider(resource=resource, id_generator=AwsXRayIdGenerator())
processor = BatchSpanProcessor(OTLPSpanExporter())
tracer_provider.add_span_processor(processor)

# Sets the global default tracer provider
trace.set_tracer_provider(tracer_provider)

# Creates a tracer from the global tracer provider
tracer = trace.get_tracer(__name__)

# Setup metrics
reader = PrometheusMetricReader()
meter_provider = MeterProvider(resource=resource, metric_readers=[reader])

# Sets the global default meter provider
metrics.set_meter_provider(meter_provider)

# Creates a meter from the global meter provider
meter = metrics.get_meter(__name__)

def transactions_history_callback(result):
    count = repository.count_transaction_history(db)
    yield Observation(count)

meter.create_observable_gauge(
    name="transactions_history.count",
    description="The number of items in the transactions history",
    callbacks=[transactions_history_callback])

transactions_get_counter = meter.create_counter(
    "transactions_get.count",
    description="The number of times the transactions_get endpoint has been called",
)

# This exposes the /metrics HTTP endpoint
metrics = PrometheusMetrics(app, group_by='endpoint')

@app.route('/petadoptionshistory/api/home/transactions', methods=['GET'])
def transactions_get():
    with tracer.start_as_current_span("transactions_get") as transactions_span:
        transactions_get_counter.add(1)
        transactions = repository.list_transaction_history(db)
        return jsonify(transactions)

@app.route('/petadoptionshistory/api/home/transactions', methods=['DELETE'])
def transactions_delete():
    with tracer.start_as_current_span("transactions_delete") as transactions_span:
        repository.delete_transaction_history(db)
        return jsonify(success=True)

@app.route('/health/status')
def status_path():
    repository.check_alive(db)
    return jsonify(success=True)