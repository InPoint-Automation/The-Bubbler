# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Florence-2 ONNX reader. Optional Path-B VLM. UN-VALIDATED.
import os
import re

# Task token -> processor prompt text.
_TASK = "<OCR_WITH_REGION>"
_TASK_PROMPTS = {
    "<OCR>": "What is the text in the image?",
    "<OCR_WITH_REGION>": "What is the text in the image, with regions?",
}

# ImageNet normalisation + square input size.
_IMG_SIZE = 768
_MEAN = (0.485, 0.456, 0.406)
_STD = (0.229, 0.224, 0.225)

# BART special ids: pad=1, bos=0, eos=2, decoder_start=2.
_DECODER_START = 2
_EOS = 2
_MAX_NEW_TOKENS = 1024

# Graph stem -> accepted basenames, first existing wins.
_GRAPHS = {
    "vision_encoder": ("vision_encoder", "vision_encoder_fp16",
                       "vision_encoder_int8", "vision_encoder_quantized"),
    "embed_tokens": ("embed_tokens", "embed_tokens_fp16",
                     "embed_tokens_int8", "embed_tokens_quantized"),
    "encoder_model": ("encoder_model", "encoder_model_fp16",
                      "encoder_model_int8", "encoder_model_quantized"),
    "decoder_model_merged": ("decoder_model_merged", "decoder_model_merged_fp16",
                             "decoder_model_merged_int8",
                             "decoder_model_merged_quantized"),
}

_LOC = re.compile(r"<loc_(\d+)>")
# Text run plus its 8 quad-corner loc tokens.
_SEG = re.compile(r"(.+?)((?:<loc_\d+>){8})", re.S)
_SPECIAL = re.compile(r"</?s>|<pad>")              # BART specials

# Bundled-default packs, searched in order.
_DEFAULT_PACKS = ("florence2", "florence2-base-ft")


def _model_roots(model_root=None):
    """Candidate bubbler/models dirs in priority order."""
    import sys
    roots = []
    if model_root:
        roots.append(model_root)
    here = os.path.dirname(os.path.abspath(__file__))
    roots.append(os.path.join(here, "models"))
    try:
        base = __compiled__.containing_dir
        roots.append(os.path.join(base, "models"))
        roots.append(os.path.join(base, "bubbler", "models"))
    except NameError:
        pass
    base = getattr(sys, "_MEIPASS", None)
    if base:
        roots.append(os.path.join(base, "models"))
        roots.append(os.path.join(base, "bubbler", "models"))
    return roots


def model_dir(cfg, model_root=None):
    """Resolve the Florence-2 pack directory, or None."""
    roots = _model_roots(model_root)
    p = (cfg or {}).get("vision_vlm_model")
    if p:
        if os.path.isdir(p):
            return p
        for root in roots:
            cand = os.path.join(root, p)
            if os.path.isdir(cand):
                return cand
    for root in roots:
        for name in _DEFAULT_PACKS:
            cand = os.path.join(root, name)
            if os.path.isdir(cand):
                return cand
    return None


def _find_graph(onnx_dir, names):
    for n in names:
        cand = os.path.join(onnx_dir, n + ".onnx")
        if os.path.exists(cand):
            return cand
    return None


def _is_pack(d):
    """True if d has tokenizer + all four graphs."""
    if not os.path.isdir(d) or not os.path.exists(
            os.path.join(d, "tokenizer.json")):
        return False
    onnx_dir = os.path.join(d, "onnx")
    if not os.path.isdir(onnx_dir):
        onnx_dir = d
    return all(_find_graph(onnx_dir, names) for names in _GRAPHS.values())


def list_packs(model_root=None):
    """Valid florence2* pack basenames, first root wins."""
    out, seen = [], set()
    for root in _model_roots(model_root):
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            if name in seen or not name.startswith("florence2"):
                continue
            if _is_pack(os.path.join(root, name)):
                seen.add(name)
                out.append(name)
    return out


def can_load(cfg, model_root=None):
    """Cheap availability probe before load."""
    mp = model_dir(cfg, model_root)
    if mp is None:
        return False
    onnx_dir = os.path.join(mp, "onnx")
    if not os.path.isdir(onnx_dir):
        onnx_dir = mp
    if not os.path.exists(os.path.join(mp, "tokenizer.json")):
        return False
    for names in _GRAPHS.values():
        if _find_graph(onnx_dir, names) is None:
            return False
    try:
        import numpy            # noqa: F401
        import onnxruntime      # noqa: F401
        import tokenizers       # noqa: F401
    except Exception:
        return False
    return True


class Florence2:
    """Lazily-loaded Florence-2 ONNX reader. Construct via ``load``."""

    def __init__(self, sessions, tok, np):
        self._s = sessions
        self._tok = tok
        self._np = np
        self._warmed = False
        # decoder KV layout from graph IO names
        self._dec_past_in = [i.name for i in
                             sessions["decoder_model_merged"].get_inputs()
                             if i.name.startswith("past_key_values")]
        self._dec_has_cache_branch = any(
            i.name == "use_cache_branch"
            for i in sessions["decoder_model_merged"].get_inputs())

    @classmethod
    def load(cls, providers, model_path):
        """Open the four graphs + tokenizer, or None."""
        if model_path is None:
            return None
        onnx_dir = os.path.join(model_path, "onnx")
        if not os.path.isdir(onnx_dir):
            onnx_dir = model_path
        tok_json = os.path.join(model_path, "tokenizer.json")
        try:
            import numpy as np
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except Exception:
            return None
        if not os.path.exists(tok_json):
            return None
        sessions = {}
        for stem, names in _GRAPHS.items():
            path = _find_graph(onnx_dir, names)
            if path is None:
                return None
            sessions[stem] = ort.InferenceSession(path, providers=providers)
        tok = Tokenizer.from_file(tok_json)
        return cls(sessions, tok, np)

    def read_regions(self, img_rgb):
        """OCR_WITH_REGION -> (quad_box, text, 1.0) in crop pixels."""
        np = self._np
        h, w = img_rgb.shape[0], img_rgb.shape[1]
        if h < 2 or w < 2:
            return []
        pixel_values = self._preprocess(img_rgb)
        enc = self._encode(pixel_values)
        text = self._generate(enc)
        return self._post(text, w, h)

    def _preprocess(self, img_rgb):
        np = self._np
        arr = self._resize(img_rgb, _IMG_SIZE, _IMG_SIZE)
        arr = arr.astype("float32") / 255.0
        mean = np.array(_MEAN, dtype="float32").reshape(1, 1, 3)
        std = np.array(_STD, dtype="float32").reshape(1, 1, 3)
        arr = (arr - mean) / std
        arr = np.transpose(arr, (2, 0, 1))[None]          # NCHW
        return np.ascontiguousarray(arr, dtype="float32")

    def _resize(self, img_rgb, out_w, out_h):
        np = self._np
        try:
            from PIL import Image
            im = Image.fromarray(img_rgb).resize((out_w, out_h), Image.BILINEAR)
            return np.asarray(im)
        except Exception:
            # nearest-neighbour fallback
            yi = (np.linspace(0, img_rgb.shape[0] - 1, out_h)).astype("int64")
            xi = (np.linspace(0, img_rgb.shape[1] - 1, out_w)).astype("int64")
            return img_rgb[yi][:, xi]

    def _embed(self, input_ids):
        s = self._s["embed_tokens"]
        name = s.get_inputs()[0].name
        return s.run(None, {name: input_ids})[0]

    def _encode(self, pixel_values):
        """Vision encoder + text embed -> (encoder_hidden_states, mask)."""
        np = self._np
        vis = self._s["vision_encoder"]
        image_features = vis.run(
            None, {vis.get_inputs()[0].name: pixel_values})[0]
        ids = self._tok.encode(_TASK_PROMPTS[_TASK]).ids
        input_ids = np.array([ids], dtype="int64")
        text_embeds = self._embed(input_ids)
        inputs_embeds = np.concatenate([image_features, text_embeds], axis=1)
        attn = np.ones(inputs_embeds.shape[:2], dtype="int64")
        enc = self._s["encoder_model"]
        feed = {}
        for i in enc.get_inputs():
            if i.name == "inputs_embeds":
                feed[i.name] = inputs_embeds
            elif i.name == "attention_mask":
                feed[i.name] = attn
        enc_hidden = enc.run(None, feed)[0]
        return enc_hidden, attn

    def _empty_past(self):
        """Zero-length past_key_values so the decoder runs its no-cache branch."""
        np = self._np
        dec = self._s["decoder_model_merged"]
        shapes = {i.name: i.shape for i in dec.get_inputs()}
        past = {}
        for name in self._dec_past_in:
            dims = []
            for d in shapes[name]:
                if isinstance(d, int):
                    dims.append(d)
                elif "head" in str(d) and "dim" not in str(d):
                    dims.append(12)            # num_heads
                else:
                    dims.append(0)             # symbolic
            # [batch, heads, seq, head_dim]
            if len(dims) == 4:
                dims[0] = 1
                dims[2] = 0
                if dims[3] in (0, None):
                    dims[3] = 64
                if dims[1] in (0, None):
                    dims[1] = 12
            past[name] = np.zeros([d if isinstance(d, int) else 0 for d in dims],
                                  dtype="float32")
        return past

    def _generate(self, enc):
        np = self._np
        enc_hidden, enc_attn = enc
        dec = self._s["decoder_model_merged"]
        in_names = {i.name for i in dec.get_inputs()}
        out_names = [o.name for o in dec.get_outputs()]
        present_map = {o: o.replace("present", "past_key_values")
                       for o in out_names if o.startswith("present")}
        # cross-attn KV reused; overwriting corrupts it
        dec_present = {o: p for o, p in present_map.items() if ".decoder." in o}
        enc_present = {o: p for o, p in present_map.items() if ".encoder." in o}
        generated = [_DECODER_START]
        past = self._empty_past()
        use_cache = False
        for _step in range(_MAX_NEW_TOKENS):
            if use_cache:
                dec_ids = np.array([[generated[-1]]], dtype="int64")
            else:
                dec_ids = np.array([generated], dtype="int64")
            feed = {}
            if "input_ids" in in_names:
                feed["input_ids"] = dec_ids
            if "encoder_hidden_states" in in_names:
                feed["encoder_hidden_states"] = enc_hidden
            if "encoder_attention_mask" in in_names:
                feed["encoder_attention_mask"] = enc_attn
            for k, v in past.items():
                if k in in_names:
                    feed[k] = v
            if self._dec_has_cache_branch:
                feed["use_cache_branch"] = np.array([use_cache], dtype="bool")
            outputs = dec.run(None, feed)
            od = dict(zip(out_names, outputs))
            logits = od["logits"] if "logits" in od else outputs[0]
            next_id = int(np.argmax(logits[0, -1]))
            if next_id == _EOS and len(generated) > 1:
                break
            generated.append(next_id)
            # keep cross-attn KV from step 1
            new_past = {pkv: od[o] for o, pkv in dec_present.items()}
            for o, pkv in enc_present.items():
                new_past[pkv] = od[o] if not use_cache else past[pkv]
            if new_past:
                past = new_past
                use_cache = True
        return self._tok.decode(generated[1:], skip_special_tokens=False)

    def _post(self, text, w, h):
        """Parse '<run><loc x8>...' into (quad_box, text, 1.0) in crop pixels."""
        out = []
        for m in _SEG.finditer(text):
            label = _SPECIAL.sub("", m.group(1)).strip()
            locs = [int(x) for x in _LOC.findall(m.group(2))]
            if len(locs) < 8 or not label:
                continue
            # bins -> pixels at bin centre, num_bins=1000
            pts = []
            for i in range(0, 8, 2):
                x = (locs[i] + 0.5) / 1000.0 * w
                y = (locs[i + 1] + 0.5) / 1000.0 * h
                pts.append((x, y))
            out.append((pts, label, 1.0))
        return out

    def warmup(self):
        """One dummy pass to JIT DirectML shaders off critical path."""
        if self._warmed:
            return
        self._warmed = True
        try:
            import numpy as np
            self.read_regions(np.full((64, 256, 3), 255, dtype="uint8"))
        except Exception:
            pass