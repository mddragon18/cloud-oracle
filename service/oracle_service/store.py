"""Results store: put / latest / since for kinds forecast, plan, alert."""
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .config import Config

KINDS = ("forecast", "plan", "alert")
TTL_DAYS = 30


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def cutoff_iso(days: float) -> str:
    return iso(datetime.now(UTC) - timedelta(days=days))


def _check(kind: str):
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}")


class LocalStore:
    """data/<kind>/<generated_at>.json, plus data/<kind>.out.json for the old stub readers."""

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)

    def put(self, kind: str, doc: dict) -> None:
        _check(kind)
        d = self.data_dir / kind
        d.mkdir(parents=True, exist_ok=True)
        text = json.dumps(doc, indent=2)
        (d / (doc["generated_at"].replace(":", "-") + ".json")).write_text(text)
        if kind != "alert":
            (self.data_dir / f"{kind}.out.json").write_text(text)

    def _all(self, kind: str) -> list[dict]:
        _check(kind)
        d = self.data_dir / kind
        files = sorted(d.glob("*.json"), reverse=True) if d.is_dir() else []
        return [json.loads(f.read_text()) for f in files]

    def latest(self, kind: str) -> dict | None:
        docs = self._all(kind)
        return docs[0] if docs else None

    def since(self, kind: str, days: float) -> list[dict]:
        cut = cutoff_iso(days)
        return [d for d in self._all(kind) if d["generated_at"] >= cut]


class DynamoStore:
    """Table PK kind (S), SK generated_at (S), body = JSON string (no Decimal issues), ttl 30 days."""

    def __init__(self, table: str, region: str, resource=None):
        self.table_name, self.region, self._resource = table, region, resource
        self._table = None

    @property
    def table(self):
        if self._table is None:
            if self._resource is None:
                import boto3
                self._resource = boto3.resource("dynamodb", region_name=self.region)
            self._table = self._resource.Table(self.table_name)
        return self._table

    def put(self, kind: str, doc: dict) -> None:
        _check(kind)
        self.table.put_item(Item={"kind": kind, "generated_at": doc["generated_at"],
                                  "body": json.dumps(doc), "ttl": int(time.time()) + TTL_DAYS * 86400})

    def latest(self, kind: str) -> dict | None:
        from boto3.dynamodb.conditions import Key
        items = self.table.query(KeyConditionExpression=Key("kind").eq(kind),
                                 ScanIndexForward=False, Limit=1)["Items"]
        return json.loads(items[0]["body"]) if items else None

    def since(self, kind: str, days: float) -> list[dict]:
        from boto3.dynamodb.conditions import Key
        cond = Key("kind").eq(kind) & Key("generated_at").gte(cutoff_iso(days))
        kwargs = {"KeyConditionExpression": cond, "ScanIndexForward": False}
        out = []
        while True:
            resp = self.table.query(**kwargs)
            out += [json.loads(i["body"]) for i in resp["Items"]]
            if "LastEvaluatedKey" not in resp:
                return out
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


def get_store(cfg: Config):
    if cfg.store == "local":
        return LocalStore(cfg.data_dir)
    if cfg.store == "dynamo":
        return DynamoStore(cfg.results_table, cfg.aws_region)
    raise ValueError(f"unknown ORACLE_STORE {cfg.store!r}")
