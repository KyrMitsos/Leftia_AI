import hashlib
import json
import os


def canonical_bytes(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def state_hash(data):
    return hashlib.sha256(canonical_bytes(data)).hexdigest()


def read_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as infile:
            return json.load(infile)
    except Exception:
        return None


def atomic_write_json(data, path, backup=True):
    payload = canonical_bytes(data)
    temp_path = path + '.tmp'
    backup_path = path + '.bak'
    with open(temp_path, 'wb') as outfile:
        outfile.write(payload)
        outfile.flush()
        os.fsync(outfile.fileno())
    if backup and os.path.isfile(path):
        os.replace(path, backup_path)
    os.replace(temp_path, path)
    try:
        directory = os.path.dirname(os.path.abspath(path)) or '.'
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except Exception:
        pass
    return hashlib.sha256(payload).hexdigest()
