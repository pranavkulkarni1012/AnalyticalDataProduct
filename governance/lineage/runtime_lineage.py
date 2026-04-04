"""
Runtime Lineage Tracker

Captures execution metadata with correlation IDs during pipeline runs.
Designed to be called from any compute engine (Glue, EMR, Lambda, ECS)
to record runtime lineage events that complement static lineage.

Correlation ID propagation:
    1. Step Function generates a UUID correlation_id at start
    2. Passed to Glue/EMR via --correlation_id job parameter
    3. Passed to Lambda via event["correlation_id"]
    4. Passed to ECS via CORRELATION_ID environment variable
    5. All structured log entries include the correlation_id
    6. Runtime lineage events are written to S3 for querying

Usage (in generated ETL code):
    from governance.lineage.runtime_lineage import RuntimeLineageTracker

    tracker = RuntimeLineageTracker(
        product_name="monthly_revenue_by_category",
        correlation_id=correlation_id,
        environment="prod",
    )
    tracker.record_source_read("customer_orders", row_count=50000)
    tracker.record_source_read("product_catalog", row_count=200)
    tracker.record_transform("join", input_rows=50000, output_rows=49800)
    tracker.record_target_write("monthly_revenue_by_category", row_count=156)
    tracker.record_reconciliation("PASS", details={...})
    tracker.finalize()       # writes lineage event to S3/CloudWatch
"""
import json
import logging
import uuid
from datetime import datetime, timezone


class RuntimeLineageTracker:
    """
    Tracks runtime lineage events during pipeline execution.

    Collects source reads, transformations, target writes, and
    reconciliation results into a structured lineage event document
    tagged with a correlation ID for cross-service tracing.

    Attributes:
        product_name: Name of the data product.
        correlation_id: UUID for tracing across services.
        environment: Deployment environment (dev/staging/prod).
    """

    def __init__(self, product_name, correlation_id=None, environment="dev",
                 logger=None):
        self.product_name = product_name
        self.correlation_id = correlation_id or str(uuid.uuid4())
        self.environment = environment
        self.logger = logger or logging.getLogger(__name__)

        self.start_time = datetime.now(timezone.utc)
        self.events = []
        self.source_reads = []
        self.transforms = []
        self.target_writes = []
        self.reconciliation_result = None
        self.data_quality_result = None

        self.logger.info(
            "RuntimeLineageTracker initialized "
            f"(product={product_name}, correlation_id={self.correlation_id})"
        )

    def record_source_read(self, source_name, row_count, duration_seconds=None,
                           metadata=None):
        """Record a source read event."""
        event = {
            "event_type": "source_read",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_name": source_name,
            "row_count": row_count,
            "duration_seconds": duration_seconds,
            "metadata": metadata or {},
        }
        self.source_reads.append(event)
        self.events.append(event)
        self.logger.info(
            f"Source read: {source_name} ({row_count} rows)"
        )

    def record_transform(self, transform_name, input_rows=None,
                         output_rows=None, duration_seconds=None,
                         metadata=None):
        """Record a transformation step event."""
        event = {
            "event_type": "transform",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "transform_name": transform_name,
            "input_rows": input_rows,
            "output_rows": output_rows,
            "duration_seconds": duration_seconds,
            "metadata": metadata or {},
        }
        self.transforms.append(event)
        self.events.append(event)
        self.logger.info(
            f"Transform: {transform_name} "
            f"({input_rows} -> {output_rows} rows)"
        )

    def record_target_write(self, target_name, row_count,
                            duration_seconds=None, metadata=None):
        """Record a target write event."""
        event = {
            "event_type": "target_write",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "target_name": target_name,
            "row_count": row_count,
            "duration_seconds": duration_seconds,
            "metadata": metadata or {},
        }
        self.target_writes.append(event)
        self.events.append(event)
        self.logger.info(
            f"Target write: {target_name} ({row_count} rows)"
        )

    def record_reconciliation(self, status, details=None):
        """Record the reconciliation result."""
        self.reconciliation_result = {
            "event_type": "reconciliation",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "details": details or {},
        }
        self.events.append(self.reconciliation_result)
        self.logger.info(f"Reconciliation: {status}")

    def record_data_quality(self, status, details=None):
        """Record the data quality check result."""
        self.data_quality_result = {
            "event_type": "data_quality",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "details": details or {},
        }
        self.events.append(self.data_quality_result)
        self.logger.info(f"Data quality: {status}")

    def finalize(self):
        """
        Build and return the complete runtime lineage document.

        Returns a structured dict suitable for JSON serialization and
        storage in S3 or a lineage catalog.
        """
        end_time = datetime.now(timezone.utc)
        duration_seconds = (end_time - self.start_time).total_seconds()

        total_source_rows = sum(s["row_count"] or 0 for s in self.source_reads)
        total_target_rows = sum(t["row_count"] or 0 for t in self.target_writes)

        lineage_doc = {
            "metadata": {
                "product_name": self.product_name,
                "correlation_id": self.correlation_id,
                "environment": self.environment,
                "start_time": self.start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration_seconds": round(duration_seconds, 2),
                "status": self._derive_status(),
            },
            "summary": {
                "source_count": len(self.source_reads),
                "transform_count": len(self.transforms),
                "target_count": len(self.target_writes),
                "total_source_rows": total_source_rows,
                "total_target_rows": total_target_rows,
                "reconciliation_status": (
                    self.reconciliation_result.get("status")
                    if self.reconciliation_result else None
                ),
                "data_quality_status": (
                    self.data_quality_result.get("status")
                    if self.data_quality_result else None
                ),
            },
            "source_reads": self.source_reads,
            "transforms": self.transforms,
            "target_writes": self.target_writes,
            "reconciliation": self.reconciliation_result,
            "data_quality": self.data_quality_result,
        }

        self.logger.info(
            f"Runtime lineage finalized: {len(self.events)} events, "
            f"{duration_seconds:.1f}s total"
        )

        return lineage_doc

    def _derive_status(self):
        """Derive overall pipeline status from recorded events."""
        if self.reconciliation_result:
            if self.reconciliation_result.get("status") == "FAIL":
                return "FAILED_RECONCILIATION"
        if self.data_quality_result:
            if self.data_quality_result.get("status") == "FAIL":
                return "FAILED_DATA_QUALITY"
        if not self.target_writes:
            return "INCOMPLETE"
        return "SUCCEEDED"

    def to_json(self, indent=2):
        """Return the finalized lineage document as a JSON string."""
        return json.dumps(self.finalize(), indent=indent)
