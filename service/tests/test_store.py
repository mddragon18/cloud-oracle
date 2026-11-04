import boto3
import pytest
from moto import mock_aws

from service.oracle_service.store import DynamoStore, LocalStore, cutoff_iso

DOCS = [{"generated_at": cutoff_iso(10)}, {"generated_at": cutoff_iso(2)}, {"generated_at": cutoff_iso(1)}]


def docs():
    return DOCS


def check(store):
    assert store.latest("plan") is None
    for d in docs():
        store.put("plan", d)
    assert store.latest("plan") == docs()[2]
    got = store.since("plan", 7)
    assert [d["generated_at"] for d in got] == [docs()[2]["generated_at"], docs()[1]["generated_at"]]
    with pytest.raises(ValueError):
        store.put("nope", {})


def test_local(tmp_path):
    check(LocalStore(tmp_path))
    assert (tmp_path / "plan.out.json").exists()


@mock_aws
def test_dynamo():
    ddb = boto3.resource("dynamodb", region_name="ap-south-1")
    ddb.create_table(TableName="t", BillingMode="PAY_PER_REQUEST",
                     KeySchema=[{"AttributeName": "kind", "KeyType": "HASH"},
                                {"AttributeName": "generated_at", "KeyType": "RANGE"}],
                     AttributeDefinitions=[{"AttributeName": "kind", "AttributeType": "S"},
                                           {"AttributeName": "generated_at", "AttributeType": "S"}])
    check(DynamoStore("t", "ap-south-1", resource=ddb))
