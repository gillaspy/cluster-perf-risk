"""A small in-memory VCF Operations Suite API for collect() tests: answers the
resource query and the three bulk reads, records every call."""
from unittest import mock


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self.ok = status < 400
        self._body = body or {}
        self.text = ""

    def json(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def rkey(name, kind, objid, vcid="vc1"):
    return {
        "name": name, "adapterKindKey": "VMWARE", "resourceKindKey": kind,
        "resourceIdentifiers": [
            {"identifierType": {"name": "VMEntityObjectID", "isPartOfUniqueness": True}, "value": objid},
            {"identifierType": {"name": "VMEntityVCID", "isPartOfUniqueness": True}, "value": vcid},
        ],
    }


class Estate:
    """resources: {id: resourceKey}; children: {parent_id: [child_id]};
    stats: {id: {statKey as returned: value}}; properties: {id: {key: value}}"""

    def __init__(self, resources, children, stats, properties):
        self.resources = resources
        self.children = children
        self.stats = stats
        self.properties = properties


class FakeClient:
    def __init__(self, estate, token="t", status=None):
        self.estate = estate
        self.token = ""
        self._token = token
        self.status = status or {}  # {url suffix: forced HTTP status}
        self.credential = mock.Mock(host="https://ops.example.test/suite-api/")
        self.calls = []

    def _to_vrops_request(self, url, **kw):
        return kw

    def __enter__(self):
        self.token = self._token
        return self

    def __exit__(self, *a):
        self.token = ""

    def get(self, url, **kw):
        raise AssertionError(f"unexpected per-resource GET {url}")

    def post(self, url, **kw):
        self.calls.append((url, kw))
        for suffix, status in self.status.items():
            if url.endswith(suffix):
                return Resp(status)
        body = kw.get("json", {})
        e = self.estate
        if url == "/api/resources/query":
            kind = body["resourceKind"][0]
            rl = [{"identifier": i, "resourceKey": k} for i, k in e.resources.items() if k["resourceKindKey"] == kind]
            return Resp(body={"resourceList": rl, "pageInfo": {"totalCount": len(rl)}})
        if url == "/api/resources/bulk/relationships":
            related = {}
            for parent in body["resourceIds"]:
                for child in e.children.get(parent, []):
                    related.setdefault(child, []).append(parent)
            rels = [{"resource": {"identifier": c, "resourceKey": e.resources[c]}, "relatedResources": p}
                    for c, p in related.items()]
            return Resp(body={"resourcesRelations": rels, "pageInfo": {"totalCount": len(rels)}})
        if url == "/api/resources/stats/latest/query":
            values = []
            for rid in body["resourceId"]:
                stats = [{"statKey": {"key": k}, "data": [v]} for k, v in e.stats.get(rid, {}).items()
                         if k in body["statKey"] or k.split(":", 1)[0] + "|" + k.split("|", 1)[1] in body["statKey"]]
                if stats:
                    values.append({"resourceId": rid, "stat-list": {"stat": stats}})
            return Resp(body={"values": values})
        if url == "/api/resources/properties/latest/query":
            values = []
            for rid in body["resourceIds"]:
                pc = [{"statKey": k, "values": [v]} for k, v in e.properties.get(rid, {}).items()
                      if k in body["propertyKeys"]]
                if pc:
                    values.append({"resourceId": rid, "property-contents": {"property-content": pc}})
            return Resp(body={"values": values})
        raise AssertionError(f"unexpected POST {url}")


class Instance:
    def __init__(self, client):
        self.client = client

    def get_suite_api_client(self):
        return self.client

    def get_identifier_value(self, key, default=None):
        return default
