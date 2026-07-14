# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# ONNX runner.

import json
import struct
import sys


def _read(stream, n):
    buf = b""
    while len(buf) < n:
        chunk = stream.read(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def recv(stream):
    hlen = _read(stream, 4)
    if hlen is None:
        return None
    header = json.loads(_read(stream, struct.unpack(">I", hlen)[0]))
    blobs = [_read(stream, n) for n in header.get("blob_lens", [])]
    return header, blobs


def send(stream, header, blobs=()):
    header = dict(header)
    header["blob_lens"] = [len(b) for b in blobs]
    hb = json.dumps(header).encode("utf-8")
    stream.write(struct.pack(">I", len(hb)))
    stream.write(hb)
    for b in blobs:
        stream.write(b)
    stream.flush()


def main():
    import numpy as np
    import onnxruntime as ort

    try:
        ort.preload_dlls(directory="")
    except Exception:
        pass

    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    sessions = {}

    def session(path):
        s = sessions.get(path)
        if s is None:
            s = ort.InferenceSession(path, providers=providers)
            sessions[path] = s
        return s

    inp, outp = sys.stdin.buffer, sys.stdout.buffer
    while True:
        msg = recv(inp)
        if msg is None:
            return
        header, blobs = msg
        cmd = header.get("cmd")
        try:
            if cmd == "ping":
                send(outp, {"ok": True, "ort": ort.__version__,
                            "providers": list(ort.get_available_providers())})
            elif cmd == "meta":
                s = session(header["model"])
                send(outp, {"ok": True,
                            "inputs": [i.name for i in s.get_inputs()],
                            "outputs": [{"name": o.name, "shape": o.shape}
                                        for o in s.get_outputs()],
                            "providers": list(s.get_providers())})
            elif cmd == "run":
                s = session(header["model"])
                feed = {}
                for name, spec, blob in zip(header["input_names"],
                                            header["input_specs"], blobs):
                    feed[name] = np.frombuffer(
                        blob, dtype=spec["dtype"]).reshape(spec["shape"])
                outs = s.run(header.get("output_names"), feed)
                specs = [{"dtype": str(o.dtype), "shape": list(o.shape)}
                         for o in outs]
                send(outp, {"ok": True, "output_specs": specs,
                            "providers": list(s.get_providers())},
                     [np.ascontiguousarray(o).tobytes() for o in outs])
            else:
                send(outp, {"ok": False, "error": "bad cmd %r" % cmd})
        except Exception as e:
            send(outp, {"ok": False, "error": "%s: %s"
                        % (type(e).__name__, e)})


if __name__ == "__main__":
    main()
