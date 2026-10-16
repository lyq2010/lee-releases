"""Mirror verification must never read object bodies, including through public proxies."""
import urllib.parse


def verify_sizes(expected, actual):
    for key, size in expected.items():
        if key not in actual or int(actual[key]) != size:
            raise SystemExit(f"Remote object missing or size mismatch: {key}")
    print("远端对象存在且大小匹配；远端正文、版本和哈希未验证（禁止下载补验）。")


def verify_cos(client, bucket, expected):
    verify_sizes(expected, {
        key: client.head_object(Bucket=bucket, Key=key)["Content-Length"]
        for key in expected
    })


def r2_objects(request, path, prefix):
    objects, cursor, seen = {}, "", set()
    while True:
        params = {"prefix": prefix, "per_page": "1000"}
        if cursor:
            params["cursor"] = cursor
        page = request("GET", path, params)
        objects.update({item["key"]: item for item in page.get("result") or []})
        info = page.get("result_info") or {}
        next_cursor = info.get("cursor") or ""
        if not next_cursor and not info.get("is_truncated"):
            return objects
        if not next_cursor or next_cursor in seen:
            raise SystemExit("Invalid R2 listing cursor")
        seen.add(next_cursor)
        cursor = next_cursor


def verify_r2(request, path, expected):
    actual = {}
    for key in expected:
        item = r2_objects(request, path, key).get(key)
        if item is not None:
            actual[key] = item["size"]
    verify_sizes(expected, actual)


def r2_path(account, bucket):
    return (f"/accounts/{urllib.parse.quote(account, safe='')}/r2/buckets/"
            f"{urllib.parse.quote(bucket, safe='')}/objects")
