import base64, hashlib, hmac, io, json, math, os, sys, threading, time, uuid, webbrowser
import urllib.request, urllib.error, urllib.parse
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageDraw, ImageTk

import keyring
import mss, mss.tools
from openai import OpenAI, RateLimitError
from pynput import keyboard

# Mantém a pasta e o nome do serviço antigos para não perder contas e chaves já salvas.
APP_DIR = Path.home() / ".boy_scripts"
APP_DIR.mkdir(exist_ok=True)
SHOT = APP_DIR / "ultima_questao.png"
CFG = APP_DIR / "config.json"
SERVICE = "BoyScripts"
BASE_DIR = Path(__file__).resolve().parent

APP_NAME = "Universo Bot"
APP_VERSION = "1.0.0"
APP_LOGO_FILE = "UniBotLogo.png"
DEFAULT_UNIVERSAL_URL = "https://openrouter.ai/api/v1"

# ---------- LicenseAuth: cada conta fica presa a uma key e você controla tudo pelo painel ----------
LA_URL = "https://licenseauth.help/api/1.3/"
LA_NAME = "Plurall Bot"
LA_OWNERID = "6Hrk7LgpWV"
LA_SECRET = "COLOCA A SECRET AQUI CARALHO"          # cole aqui o secret NOVO (painel > Manage App > Refresh App Secret)
LA_VERSION = "1.0"      # precisa ser igual à versão cadastrada no painel
LICENSE_CHECK_MS = 120_000   # de 2 em 2 minutos o app confere se a licença/conta continua ativa

# ---------- tema (mude as cores aqui) ----------
BG = "#0c0c11"
FIELD = "#17171f"
BORDER = "#2a2a38"
TEXT = "#eeeef4"
MUTED = "#8a8a9a"
ACCENT = "#7c6cff"
ACCENT_HOVER = "#9486ff"
PANEL = "#0f0f15"
MENU = "#202024"
FONT = "Segoe UI"
FONT_LIGHT = "Segoe UI Light"
FONT_SEMI = "Segoe UI Semibold"

TOAST_COLORS = {
    "error": ("#2b1217", "#ff8d99"),
    "ok": ("#10261a", "#6ee7a0"),
    "warn": ("#2b2210", "#ffcf6b"),
    "info": (FIELD, TEXT),
}

# Provedores disponíveis. "models" = sugestões (o campo de modelo é editável,
# então dá pra digitar qualquer modelo novo que o provedor lançar).
PROVIDERS = {
    "openai": {
        "label": "OpenAI (ChatGPT)",
        "models": ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"],
        "needs_key": True,
    },
    "gemini": {
        "label": "Google Gemini",
        "models": ["gemini-2.5-pro", "gemini-2.5-flash"],
        "needs_key": True,
    },
    # Mesma API do Gemini, mas só com modelos que têm nível gratuito (chave do AI Studio,
    # sem cartão). Os Pro exigem faturamento e os 2.5 só funcionam para contas antigas.
    # A ordem é a de preferência: se um modelo bater no limite grátis (cada um tem o seu),
    # o app tenta o próximo sozinho.
    "gemini_free": {
        "label": "Google Gemini (Grátis)",
        "models": ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash",
                   "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"],
        "needs_key": True,
        "free": True,
        "key_url": "https://aistudio.google.com/apikey",
    },
    "claude": {
        "label": "Anthropic Claude",
        "models": ["claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-4-5-20251001"],
        "needs_key": True,
    },
    "universal": {
        "label": "Universal (API compatível com OpenAI)",
        "models": [],
        "needs_key": False,  # servidores locais (Ollama, LM Studio) não pedem chave
    },
}


def provider_from_label(label):
    for pid, meta in PROVIDERS.items():
        if meta["label"] == label:
            return pid
    return "openai"


def load_logo(size=(88, 88)):
    # usado só no ícone da janela
    try:
        root = Path(getattr(sys, "_MEIPASS", BASE_DIR))
        img = Image.open(root / APP_LOGO_FILE).convert("RGBA")
        img.thumbnail(size, Image.LANCZOS)
        return ImageTk.PhotoImage(img)
    except Exception:
        return None


def load_logo_images(sizes=(16, 32, 48, 64, 128, 256)):
    """Carrega variantes da logo para barras de tarefas, janelas e Alt+Tab."""
    try:
        root = Path(getattr(sys, "_MEIPASS", BASE_DIR))
        with Image.open(root / APP_LOGO_FILE) as source:
            original = source.convert("RGBA")
        photos = []
        for size in sizes:
            icon = original.copy()
            icon.thumbnail((size, size), Image.LANCZOS)
            canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            canvas.alpha_composite(icon, ((size - icon.width) // 2, (size - icon.height) // 2))
            photos.append(ImageTk.PhotoImage(canvas))
        return photos
    except Exception:
        return []


def load_provider_icons(size=22):
    """Carrega os ícones dos provedores uma única vez, sempre com fallback seguro."""
    root = Path(getattr(sys, "_MEIPASS", BASE_DIR)) / "assets"
    result = {}
    for provider in ("openai", "gemini", "claude", "universal"):
        try:
            with Image.open(root / f"{provider}.png") as source:
                icon = source.convert("RGBA")
                icon.thumbnail((size, size), Image.Resampling.LANCZOS)
                result[provider] = ImageTk.PhotoImage(icon)
        except (OSError, tk.TclError):
            pass
    return result


def set_windows_app_user_model_id():
    """Usa um identificador próprio para o agrupamento/ícone da barra do Windows."""
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("BoyScripts.UniversoBot.1")
    except Exception:
        pass


def config():
    d = {"provider": "openai", "models": {}, "base_url": DEFAULT_UNIVERSAL_URL, "monitor": 0,
         "remember_user": ""}
    if CFG.exists():
        try:
            saved = json.loads(CFG.read_text(encoding="utf-8"))
            # compatibilidade com o config antigo (só tinha "model" da OpenAI)
            if "model" in saved and "models" not in saved:
                saved["models"] = {"openai": saved["model"]}
            saved.pop("model", None)
            d.update(saved)
        except: pass
    if d.get("provider") not in PROVIDERS:
        d["provider"] = "openai"
    return d

def save_config(d):
    CFG.write_text(json.dumps(d, indent=2), encoding="utf-8")

def model_for(cfg, provider):
    m = (cfg.get("models") or {}).get(provider)
    if m:
        return m
    opts = PROVIDERS[provider]["models"]
    return opts[0] if opts else ""

# ---------- ID do computador ----------
# Usado como HWID no LicenseAuth: a conta fica presa a este computador. Para trocar de PC,
# o dono reseta o HWID do usuário no painel (Users > Actions).

_MID = None

def machine_id():
    """ID estável deste computador (não muda entre execuções)."""
    global _MID
    if _MID:
        return _MID
    raw = None
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography",
                                0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
                raw = str(winreg.QueryValueEx(k, "MachineGuid")[0]).strip()
        except Exception:
            raw = None
    if not raw:
        for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            try:
                raw = Path(path).read_text().strip()
                if raw:
                    break
            except Exception:
                raw = None
    if not raw:
        # último recurso: ID aleatório guardado em arquivo (não prende de verdade, mas
        # nunca deixa o dono trancado para fora)
        f = APP_DIR / "device.id"
        try:
            raw = f.read_text().strip() if f.exists() else ""
            if not raw:
                raw = os.urandom(16).hex()
                f.write_text(raw)
        except Exception:
            raw = "fallback"
    _MID = hashlib.sha256(("UniversoBot|" + raw).encode()).hexdigest()
    return _MID



# ---------- cliente LicenseAuth ----------
# Feito sem o licenseauth.py de exemplo porque ele chama os._exit(1) em qualquer erro
# (senha errada, sem internet...), o que fecharia o app inteiro. Aqui os erros viram
# mensagens na tela. O protocolo é o mesmo: sessão com 'init', respostas assinadas com
# HMAC-SHA256 e HWID enviado no login/cadastro.

class LicenseError(Exception):
    def __init__(self, msg, net=False, session=False):
        super().__init__(msg)
        self.net, self.session = net, session


def license_msg(msg):
    """Traduz as mensagens mais comuns do servidor; o que não conhece aparece como veio."""
    m = (msg or "").strip()
    low = m.lower()
    # O painel mantém listas independentes de usuários, licenças, IPs e HWIDs.
    # Apagar os usuários não remove necessariamente um bloqueio do computador ou da chave.
    # A ordem é importante: a mensagem antiga juntava tudo em "conta ou licença" e escondia
    # a causa real, principalmente quando o servidor devolvia "IP/HWID blacklisted".
    if ("ip" in low or "address" in low) and ("banned" in low or "blacklist" in low):
        return "O endereço IP desta conexão está bloqueado no LicenseAuth."
    if "hwid" in low and ("banned" in low or "blacklist" in low):
        return "Este computador está bloqueado no LicenseAuth (HWID). Remova o bloqueio ou redefina o HWID no painel."
    if ("key" in low or "license" in low) and ("banned" in low or "blacklist" in low):
        return "Esta chave de licença está bloqueada no LicenseAuth."
    if ("user" in low or "account" in low) and ("banned" in low or "blacklist" in low):
        return "Esta conta de usuário está bloqueada no LicenseAuth."
    if "banned" in low or "blacklist" in low:
        return "O LicenseAuth recusou o cadastro por um bloqueio ativo. Verifique IP, HWID, usuário e licença no painel."
    if "expired" in low:
        return "Sua licença expirou."
    if "hwid" in low:
        return "Esta conta está presa a outro computador. Peça o reset ao vendedor."
    if "paused" in low:
        return "O aplicativo está pausado no momento."
    if ("key" in low or "license" in low) and ("already" in low or "used" in low):
        return "Essa chave de licença já foi usada."
    if ("key" in low or "license" in low) and ("invalid" in low or "not found" in low
                                               or "doesn't exist" in low or "does not exist" in low):
        return "Chave de licença inválida."
    if "already" in low or "taken" in low or "exists" in low:
        return "Esse usuário já existe."
    if any(w in low for w in ("password", "username", "user")) and any(
            w in low for w in ("invalid", "incorrect", "wrong", "not found", "doesn't", "does not")):
        return "Usuário ou senha incorretos."
    if "session" in low:
        return "Sessão expirada. Tente de novo."
    return m or "Erro desconhecido do servidor de licenças."


class LicenseClient:
    def __init__(self):
        self.sessionid, self.enckey, self.info = "", "", {}
        self.lock = threading.RLock()

    def _post(self, data, key):
        body = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(LA_URL, data=body, headers={
            "Content-Type": "application/x-www-form-urlencoded", "User-Agent": "UniversoBot"})
        try:
            with urllib.request.urlopen(req, timeout=12) as r:
                text, sig = r.read().decode("utf-8", "replace"), r.headers.get("signature", "")
        except urllib.error.HTTPError as e:
            text, sig = e.read().decode("utf-8", "replace"), e.headers.get("signature", "")
        except (urllib.error.URLError, TimeoutError, OSError):
            raise LicenseError("Sem conexão com o servidor de licenças. Verifique sua internet.",
                               net=True)
        if "LicenseAuth_Invalid" in text:
            raise LicenseError("Aplicativo não encontrado no LicenseAuth. Confira LA_NAME e LA_OWNERID.")
        want = hmac.new(key.encode(), text.encode(), hashlib.sha256).hexdigest()
        if not sig or not hmac.compare_digest(want, sig):
            raise LicenseError("Resposta do servidor não confere (sessão encerrada ou adulterada).",
                               session=True)
        try:
            return json.loads(text)
        except ValueError:
            raise LicenseError("Resposta inesperada do servidor de licenças.")

    def init(self):
        if not LA_OWNERID or not LA_SECRET:
            raise LicenseError("Licenças não configuradas: preencha LA_OWNERID e LA_SECRET "
                               "no começo do main.py.")
        sent = str(uuid.uuid4())[:16]
        self.enckey = sent + "-" + LA_SECRET
        js = self._post({"type": "init", "ver": LA_VERSION, "hash": "", "enckey": sent,
                         "name": LA_NAME, "ownerid": LA_OWNERID}, LA_SECRET)
        if js.get("message") == "invalidver":
            link = js.get("download") or ""
            if link:
                try:
                    webbrowser.open(link)
                except Exception:
                    pass
            raise LicenseError("Há uma nova versão do programa. Baixe a atualização para continuar.")
        if not js.get("success"):
            raise LicenseError(license_msg(js.get("message")))
        self.sessionid = js["sessionid"]

    def warm(self):
        """Abre a sessão em segundo plano ao iniciar, para o primeiro login ser mais rápido."""
        try:
            with self.lock:
                if not self.sessionid:
                    self.init()
        except Exception:
            pass

    def call(self, data, retry=True):
        with self.lock:
            if not self.sessionid:
                self.init()
            payload = dict(data, sessionid=self.sessionid, name=LA_NAME, ownerid=LA_OWNERID)
            try:
                js = self._post(payload, self.enckey)
            except LicenseError as e:
                if e.session and retry:      # sessão caiu: abre outra e tenta uma vez
                    self.sessionid = ""
                    return self.call(data, retry=False)
                raise
            if not js.get("success") and "session" in str(js.get("message", "")).lower() and retry:
                self.sessionid = ""
                return self.call(data, retry=False)
            return js

    def _need_ok(self, js):
        if not js.get("success"):
            raise LicenseError(license_msg(js.get("message")))
        self.info = js.get("info") or {}
        return self.info

    def register(self, user, password, key):
        return self._need_ok(self.call({"type": "register", "username": user, "pass": password,
                                        "key": key, "hwid": machine_id()}))

    def login(self, user, password):
        return self._need_ok(self.call({"type": "login", "username": user, "pass": password,
                                        "hwid": machine_id()}))

    def check(self):
        """True = sessão e licença seguem válidas. Sem internet levanta LicenseError(net=True)."""
        with self.lock:
            if not self.sessionid:
                return False
            try:
                js = self._post({"type": "check", "sessionid": self.sessionid, "name": LA_NAME,
                                 "ownerid": LA_OWNERID}, self.enckey)
            except LicenseError as e:
                if e.session:
                    return False
                raise
            return bool(js.get("success"))


def _key_name(provider):
    # a chave da OpenAI mantém o nome antigo, então quem já salvou não perde nada
    return "openai_api_key" if provider == "openai" else f"{provider}_api_key"

def api_key(provider="openai"):
    try: return keyring.get_password(SERVICE, _key_name(provider))
    except: return None

def set_api_key(provider, k):
    keyring.set_password(SERVICE, _key_name(provider), k)

def capture(monitor_index=0):
    with mss.mss() as s:
        idx = monitor_index if 0 <= monitor_index < len(s.monitors) else 0
        im = s.grab(s.monitors[idx])
        mss.tools.to_png(im.rgb, im.size, output=str(SHOT))
    return SHOT


# ---------- comunicação com os provedores ----------

class RateLimit(Exception):
    pass

def prepare_image(path, max_side=2560, quality=85):
    """JPEG reduzido (base64) pra caber nos limites de tamanho dos provedores."""
    img = Image.open(path).convert("RGB")
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode()

def http_post(url, headers, body, timeout=120):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:300]
        if e.code in (429, 503, 529):          # limite de uso ou provedor sobrecarregado
            raise RateLimit(detail)
        if e.code in (401, 403) or (e.code == 400 and ("API key not valid" in detail
                                                       or "API_KEY_INVALID" in detail)):
            raise RuntimeError("Chave de API recusada. Confira a chave nas Configurações.")
        if e.code == 404:
            raise RuntimeError("Modelo ou endereço não encontrado (404). Confira o nome do modelo e a URL nas Configurações.")
        raise RuntimeError(f"Erro {e.code} do provedor: {detail}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Falha de conexão: {e.reason}")

def _ask_openai(key, model, data, prompt, cfg):
    client = OpenAI(api_key=key)
    r = client.responses.create(
        model=model,
        reasoning={"effort": "high"},
        input=[{"role":"user","content":[
            {"type":"input_text","text":prompt},
            {"type":"input_image","image_url":"data:image/png;base64,"+data}
        ]}]
    )
    return r.output_text

def _ask_gemini(key, model, data, prompt, cfg):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    r = http_post(url, {"x-goog-api-key": key}, {
        "contents": [{"parts": [
            {"text": prompt},
            {"inline_data": {"mime_type": "image/jpeg", "data": data}},
        ]}],
        "generationConfig": {"responseMimeType": "application/json"},
    })
    parts = r["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts)

def _ask_claude(key, model, data, prompt, cfg):
    r = http_post(
        "https://api.anthropic.com/v1/messages",
        {"x-api-key": key, "anthropic-version": "2023-06-01"},
        {
            "model": model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}},
                {"type": "text", "text": prompt},
            ]}],
        },
    )
    return "".join(b.get("text", "") for b in r["content"] if b.get("type") == "text")

def _ask_universal(key, model, data, prompt, cfg):
    base = (cfg.get("base_url") or DEFAULT_UNIVERSAL_URL).strip().rstrip("/")
    if not base.lower().startswith("http"):
        raise RuntimeError("URL base inválida. Ajuste nas Configurações.")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    r = http_post(base + "/chat/completions", headers, {
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + data}},
        ]}],
    })
    content = r["choices"][0]["message"]["content"]
    if isinstance(content, list):
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return content

ASKERS = {
    "openai": _ask_openai,
    "gemini": _ask_gemini,
    "gemini_free": _ask_gemini,
    "claude": _ask_claude,
    "universal": _ask_universal,
}

def parse_json(text):
    t = (text or "").strip().replace("```json","").replace("```","").strip()
    a,b = t.find("{"), t.rfind("}")
    if a < 0 or b < 0:
        raise ValueError("Resposta inválida da IA.")
    return json.loads(t[a:b+1])

PROMPT = """Analise com MUITO cuidado esta captura de tela de uma questão de múltipla escolha do Plurall.

Faça internamente, antes de responder:
1. Localize exatamente a questão ativa/central.
2. Leia o enunciado COMPLETO.
3. Leia TODAS as alternativas.
4. Se houver gráfico, tabela, figura ou fórmula, interprete todos os dados.
5. Resolva a questão do zero.
6. Confira a conta e a alternativa escolhida antes de finalizar.
7. Identifique módulo e número do exercício APENAS se estiverem visíveis na captura atual.

Não forneça explicação ao usuário.
Retorne SOMENTE JSON válido:
{"module":"texto ou null","exercise":"texto ou null","answer":"A","confidence":0.0}

Regras:
- answer = somente a letra da alternativa correta.
- confidence = número entre 0 e 1.
- Não use resultado de questão anterior.
- Não invente módulo ou exercício.
"""

def solve(path, cfg):
    provider = cfg.get("provider", "openai")
    meta = PROVIDERS[provider]
    k = api_key(provider)
    if meta["needs_key"] and not k:
        raise RuntimeError(f"Configure sua API Key ({meta['label']}).")

    model = model_for(cfg, provider)
    if not model:
        raise RuntimeError("Escolha ou digite o nome do modelo nas Configurações.")

    if provider == "openai":
        data = base64.b64encode(path.read_bytes()).decode()
    else:
        data = prepare_image(path)

    ask = ASKERS[provider]

    order = [model]
    for fallback in meta["models"]:
        if fallback not in order:
            order.append(fallback)

    last_rate_error = None
    for candidate in order:
        try:
            try:
                text = ask(k, candidate, data, PROMPT, cfg)
            except (KeyError, IndexError, TypeError):
                raise ValueError("Resposta inesperada do provedor.")
            out = parse_json(text)
            out["answer"] = str(out.get("answer","?")).strip().upper()
            out["_model"] = f"{provider}: {candidate}"
            return out
        except (RateLimit, RateLimitError) as exc:
            last_rate_error = exc
            continue

    if last_rate_error and meta.get("free"):
        raise RuntimeError(
            "Limite do plano grátis do Gemini atingido (por minuto ou por dia). "
            "Aguarde cerca de 1 minuto e tente de novo. Se o limite diário acabou, "
            "ele renova à meia-noite no horário do Pacífico."
        )
    if last_rate_error:
        raise RuntimeError(
            "Limite temporário da API atingido em todos os modelos disponíveis. "
            "Aguarde o limite resetar e tente novamente."
        )
    raise RuntimeError("Não foi possível resolver a questão.")


def test_connection(provider, model, key, base_url=""):
    """Pedido mínimo (só texto) para confirmar se chave, modelo e URL funcionam."""
    q = "Responda apenas: ok"
    if provider == "openai":
        import openai
        try:
            OpenAI(api_key=key, timeout=30).responses.create(
                model=model, input=q, max_output_tokens=16)
        except openai.AuthenticationError:
            raise RuntimeError("Chave de API recusada. Confira a chave.")
        except openai.NotFoundError:
            raise RuntimeError("Modelo não encontrado. Confira o nome do modelo.")
        except openai.APIConnectionError:
            raise RuntimeError("Falha de conexão com a OpenAI.")
    elif provider in ("gemini", "gemini_free"):
        http_post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                  {"x-goog-api-key": key}, {"contents": [{"parts": [{"text": q}]}]}, timeout=30)
    elif provider == "claude":
        http_post("https://api.anthropic.com/v1/messages",
                  {"x-api-key": key, "anthropic-version": "2023-06-01"},
                  {"model": model, "max_tokens": 16,
                   "messages": [{"role": "user", "content": q}]}, timeout=30)
    else:
        base = (base_url or "").strip().rstrip("/")
        if not base.lower().startswith("http"):
            raise RuntimeError("URL base inválida (precisa começar com http).")
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        http_post(base + "/chat/completions", headers,
                  {"model": model, "max_tokens": 16,
                   "messages": [{"role": "user", "content": q}]}, timeout=30)


# ---------- animações ----------

_RGB_CACHE = {}


def _rgb(color):
    """Converte uma cor hex uma única vez; animações chamam isso muitas vezes."""
    key = color.lower()
    value = _RGB_CACHE.get(key)
    if value is None:
        raw = key.lstrip("#")
        value = tuple(int(raw[i:i + 2], 16) for i in (0, 2, 4))
        _RGB_CACHE[key] = value
    return value


def lerp_color(a, b, t):
    """Mistura duas cores hex (t=0 -> a, t=1 -> b)."""
    t = max(0.0, min(1.0, t))
    ca, cb = _rgb(a), _rgb(b)
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(ca, cb))

def ease_out(t): return 1 - (1 - t) ** 3
def ease_in(t): return t ** 3
def ease_in_out(t): return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2
def linear(t): return t
def ease_out_back(t):
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def render_dot(color, size=10, bg=BG, ss=8):
    """Bolinha de status com bordas suaves."""
    img = Image.new("RGB", (size * ss, size * ss), bg)
    m = 1 * ss
    ImageDraw.Draw(img).ellipse([m, m, size * ss - m, size * ss - m], fill=color)
    return img.resize((size, size), Image.LANCZOS)


def render_eye(open_, color, size=22, bg=FIELD, ss=8):
    """Olho (mostrar/ocultar). Fechado = olho com um traço na diagonal."""
    S = size * ss
    img = Image.new("RGB", (S, S), bg)
    d = ImageDraw.Draw(img)
    lw = round(1.5 * ss)
    cx, cy = S / 2, S / 2
    bw, bh = S * 0.40, S * 0.22
    pts = []
    for i in range(0, 41):
        x = -bw + 2 * bw * i / 40
        y = bh * (1 - (x / bw) ** 2) ** 0.9
        pts.append((cx + x, cy - y))
    for i in range(40, -1, -1):
        x = -bw + 2 * bw * i / 40
        y = bh * (1 - (x / bw) ** 2) ** 0.9
        pts.append((cx + x, cy + y))
    d.line(pts + [pts[0]], fill=color, width=lw, joint="curve")
    r = S * 0.11
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    if not open_:
        d.line([(cx - bw * 0.8, cy + bh * 1.5), (cx + bw * 0.8, cy - bh * 1.5)],
               fill=bg, width=lw * 3)
        d.line([(cx - bw * 0.8, cy + bh * 1.5), (cx + bw * 0.8, cy - bh * 1.5)],
               fill=color, width=lw)
    return img.resize((size, size), Image.LANCZOS)


def render_checkbox(on, size=18, bg=BG, ss=8):
    """Caixinha arredondada; marcada = roxa com um check branco."""
    S = size * ss
    img = Image.new("RGB", (S, S), bg)
    d = ImageDraw.Draw(img)
    m, r = ss, 5 * ss
    if on:
        d.rounded_rectangle([m, m, S - m, S - m], radius=r, fill=ACCENT)
        pts = [(S * 0.27, S * 0.52), (S * 0.43, S * 0.67), (S * 0.74, S * 0.34)]
        d.line(pts, fill="#ffffff", width=round(1.8 * ss), joint="curve")
        for x, y in (pts[0], pts[-1]):
            rr = 0.9 * ss
            d.ellipse([x - rr, y - rr, x + rr, y + rr], fill="#ffffff")
    else:
        d.rounded_rectangle([m, m, S - m, S - m], radius=r, fill=FIELD, outline=BORDER,
                            width=round(1.2 * ss))
    return img.resize((size, size), Image.LANCZOS)


class Clock:
    """Relógio único de animação, com um callback por quadro.

    O Tk já repinta a janela quando o callback retorna. Forçar ``update_idletasks`` e
    bloquear a thread da interface em ``DwmFlush`` a cada quadro fazia o loop acumular
    trabalho, principalmente durante resize. Um intervalo curto e estável deixa o
    compositor do sistema sincronizar o desenho sem bloquear a UI.
    """
    FRAME_MS = 8  # até 120 Hz, sem criar uma tempestade de callbacks

    def __init__(self, root):
        self.root, self.active, self.job = root, [], None

    def add(self, tw):
        if tw not in self.active:
            self.active.append(tw)
        if self.job is None:
            self.job = self.root.after(0, self._tick)

    def remove(self, tw):
        if tw in self.active:
            self.active.remove(tw)

    def _tick(self):
        self.job = None
        now = time.perf_counter()
        for tw in list(self.active):
            if tw in self.active:
                tw._advance(now)
        if not self.active:
            return
        # O after não precisa ser exato: Tween usa tempo monotônico e compensa qualquer
        # atraso. Manter a cadência previsível evita os saltos causados pelo DwmFlush.
        self.job = self.root.after(self.FRAME_MS, self._tick)


CLOCK = None   # criado pelo App


class Tween:
    """Anima um valor de 0 a 1 em 'duration' ms. Baseado em tempo (o relógio começa no
    primeiro quadro, não na criação), então fica suave mesmo se o computador engasgar."""
    def __init__(self, widget):
        self.w = widget
        self._run = None

    def run(self, duration, step, done=None, ease=ease_out):
        self.stop()
        self._run = [None, duration, step, done, ease]
        try:
            step(ease(0.0))                   # estado inicial já no quadro 0
        except tk.TclError:
            self._run = None
            return
        CLOCK.add(self)

    def _advance(self, now):
        r = self._run
        if r is None:
            CLOCK.remove(self)
            return
        if r[0] is None:
            r[0] = now
        _, duration, step, done, ease = r
        t = min(1.0, (now - r[0]) * 1000 / max(duration, 1))
        try:
            step(ease(t))
            if t >= 1.0:
                self._run = None
                CLOCK.remove(self)
                if done:
                    done()
        except tk.TclError:
            self._run = None
            CLOCK.remove(self)
        except Exception:
            import traceback
            traceback.print_exc()
            self._run = None
            CLOCK.remove(self)

    def stop(self):
        self._run = None
        if CLOCK is not None:
            CLOCK.remove(self)


# ---------- componentes visuais ----------

def spaced(s):
    """Texto em caixa alta com espaçamento entre letras (efeito 'wordmark')."""
    return "\u2003".join("\u2009".join(w) for w in s.upper().split())

def round_rect(cv, x1, y1, x2, y2, r, **kw):
    r = max(1, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = [x1+r,y1, x2-r,y1, x2,y1, x2,y1+r, x2,y2-r, x2,y2,
           x2-r,y2, x1+r,y2, x1,y2, x1,y2-r, x1,y1+r, x1,y1]
    return cv.create_polygon(pts, smooth=True, **kw)


class RoundButton(tk.Canvas):
    """Botão arredondado (pílula) com hover suave e efeito de clique.
    style = 'primary' ou 'secondary'."""
    def __init__(self, parent, text, command, style="primary", height=48, width=None,
                 font=(FONT_SEMI, 11), bg=BG):
        super().__init__(parent, height=height, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        if width:
            self.configure(width=width)
        self.text, self.command, self.h = text, command, height
        self.style, self.font, self.bgc = style, font, bg
        self.k = 0.0          # 0 = normal, 1 = hover
        self.pressed = False
        self._bg_item = self._text_item = None
        self.tw = Tween(self)
        self.bind("<Configure>", self.draw)
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)

    def _hover(self, v):
        start = self.k
        target = 1.0 if v else 0.0
        def step(t):
            self.k = start + (target - start) * t
            self.draw()
        self.tw.run(150, step)

    def _press(self, e):
        self.pressed = True
        self.draw()

    def _release(self, e):
        was = self.pressed
        self.pressed = False
        self.draw()
        if was and 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.h:
            self.command()

    def draw(self, e=None):
        w = self.winfo_width()
        if w < 10:
            return
        if self.style == "primary":
            fill = lerp_color(ACCENT, ACCENT_HOVER, self.k)
            outline, fg = fill, "#ffffff"
        else:
            fill = lerp_color(self.bgc, FIELD, self.k)
            outline, fg = lerp_color(BORDER, MUTED, self.k), TEXT
        if self.pressed:
            fill = lerp_color(fill, "#000000", 0.18)
        coords = [1, 1, w - 1, self.h - 1]
        if self._bg_item is None:
            self._bg_item = round_rect(self, *coords, self.h / 2,
                                       fill=fill, outline=outline, width=1)
            self._text_item = self.create_text(
                w / 2, self.h / 2, text=self.text, fill=fg, font=self.font)
        else:
            self.coords(self._bg_item, *round_rect_points(*coords, self.h / 2))
            self.itemconfigure(self._bg_item, fill=fill, outline=outline, width=1)
            self.coords(self._text_item, w / 2, self.h / 2 + (1 if self.pressed else 0))
            self.itemconfigure(self._text_item, text=self.text, fill=fg, font=self.font)


def round_rect_points(x1, y1, x2, y2, r):
    """Pontos de um retângulo arredondado para atualizar um item existente."""
    r = max(1, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


class Field(tk.Canvas):
    """Caixa arredondada que hospeda um campo (Entry ou Combobox) dentro.
    A borda acende suavemente quando o campo recebe foco."""
    def __init__(self, parent, make_inner, height=46, radius=14, bg=BG):
        super().__init__(parent, height=height, bg=bg, highlightthickness=0, bd=0)
        self.h, self.r = height, radius
        self.k = 0.0          # 0 = sem foco, 1 = com foco
        self.err = 0.0        # 0 = normal, 1 = borda toda vermelha (ver flash)
        self.right_w, self.rwin = 0, None
        self.tw = Tween(self)
        self.ftw = Tween(self)
        self._bg_item = None
        self.inner = make_inner(self)
        self.win = self.create_window(radius, height // 2, window=self.inner, anchor="w")
        self.bind("<Configure>", self.draw)
        self.inner.bind("<FocusIn>", lambda e: self._focus(True), add="+")
        self.inner.bind("<FocusOut>", lambda e: self._focus(False), add="+")

    def _focus(self, v):
        start = self.k
        target = 1.0 if v else 0.0
        def step(t):
            self.k = start + (target - start) * t
            self.draw()
        self.tw.run(160, step)

    def draw(self, e=None):
        w = self.winfo_width()
        if w < 10:
            return
        border = lerp_color(lerp_color(BORDER, ACCENT, self.k), "#ff8d99", self.err)
        width = 2 if self.err > 0.05 else 1
        if self._bg_item is None:
            self._bg_item = round_rect(self, 1, 1, w - 1, self.h - 1, self.r,
                                       fill=FIELD, outline=border, width=width, tags="bg")
            self.tag_lower(self._bg_item)
        else:
            self.coords(self._bg_item, *round_rect_points(1, 1, w - 1, self.h - 1, self.r))
            self.itemconfigure(self._bg_item, outline=border, width=width)
        self.itemconfigure(self.win, width=w - 2 * self.r - self.right_w)
        if self.rwin is not None:
            self.coords(self.rwin, w - self.r + 2, self.h // 2)

    def flash(self):
        """Borda pisca em vermelho duas vezes, suave, e volta ao normal (indica o erro)."""
        def step(t):
            self.err = abs(math.sin(t * math.pi * 2)) ** 0.7 * (1 - 0.45 * t)
            self.draw()
        def done():
            self.err = 0.0
            self.draw()
        self.ftw.run(900, step, done=done, ease=linear)

    def attach_right(self, widget, width):
        """Coloca um widget pequeno (ex.: olho) no canto direito, dentro do campo."""
        self.right_w = width
        self.rwin = self.create_window(0, self.h // 2, window=widget, anchor="e")
        self.draw()


class EyeToggle(tk.Label):
    """Olho para mostrar/ocultar o conteúdo de um Entry de senha/chave."""
    def __init__(self, parent, entry, bg=FIELD):
        super().__init__(parent, bg=bg, bd=0, cursor="hand2")
        self.entry, self.shown, self.hot = entry, False, False
        self.imgs = {(o, h): ImageTk.PhotoImage(render_eye(o, TEXT if h else MUTED, 22, bg))
                     for o in (True, False) for h in (True, False)}
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))
        self.bind("<Button-1>", self._toggle)
        self._refresh()

    def _refresh(self):
        self.config(image=self.imgs[(self.shown, self.hot)])

    def _hover(self, v):
        self.hot = v
        self._refresh()

    def _toggle(self, e=None):
        self.shown = not self.shown
        self.entry.config(show="" if self.shown else "•")
        self._refresh()


class Check(tk.Frame):
    """Caixinha de seleção moderna com texto ao lado."""
    def __init__(self, parent, text, checked=False, bg=BG):
        super().__init__(parent, bg=bg, cursor="hand2")
        self.value = checked
        self.imgs = {o: ImageTk.PhotoImage(render_checkbox(o, 18, bg)) for o in (True, False)}
        self.box = tk.Label(self, bg=bg, bd=0, image=self.imgs[checked])
        self.box.pack(side="left")
        self.txt = tk.Label(self, text=text, bg=bg, fg=MUTED, font=(FONT, 9))
        self.txt.pack(side="left", padx=(7, 0))
        for w in (self, self.box, self.txt):
            w.bind("<Button-1>", self.toggle)
            w.bind("<Enter>", lambda e: self.txt.config(fg=TEXT))
            w.bind("<Leave>", lambda e: self.txt.config(fg=MUTED))

    def toggle(self, e=None):
        self.value = not self.value
        self.box.config(image=self.imgs[self.value])

    def get(self):
        return self.value


class Card(tk.Canvas):
    """Painel arredondado com borda fina; o conteúdo vai em self.inner."""
    def __init__(self, parent, height, radius=18, pad=18, bg=BG, fill=PANEL):
        super().__init__(parent, height=height, bg=bg, highlightthickness=0, bd=0)
        self.h, self.r, self.pad, self.fill = height, radius, pad, fill
        self.inner = tk.Frame(self, bg=fill)
        self._bg_item = None
        self.win = self.create_window(0, height // 2, window=self.inner, anchor="w")
        self.bind("<Configure>", self.draw)

    def draw(self, e=None):
        w = self.winfo_width()
        if w < 10:
            return
        if self._bg_item is None:
            self._bg_item = round_rect(self, 1, 1, w - 1, self.h - 1, self.r,
                                       fill=self.fill, outline=BORDER, width=1, tags="bg")
            self.tag_lower(self._bg_item)
        else:
            self.coords(self._bg_item, *round_rect_points(1, 1, w - 1, self.h - 1, self.r))
            self.itemconfigure(self._bg_item, fill=self.fill, outline=BORDER, width=1)
        self.coords(self.win, self.pad, self.h // 2)
        self.itemconfigure(self.win, width=w - 2 * self.pad, height=self.h - 2 * self.pad)


class SmoothScrollbar(tk.Canvas):
    """Barra de rolagem compacta, desenhada no mesmo estilo do aplicativo."""
    WIDTH = 14
    MIN_THUMB = 34

    def __init__(self, parent, command):
        super().__init__(parent, width=self.WIDTH, bg=BG, highlightthickness=0, bd=0,
                         cursor="hand2")
        self.command, self.first, self.last = command, 0.0, 1.0
        self.hot, self.dragging, self.drag_offset = False, False, 0
        self._rail = self.create_line(7, 8, 7, 8, fill="#242431", width=4,
                                      capstyle="round")
        self._thumb = round_rect(self, 2, 8, 12, 42, 5, fill="#6255d8", outline="")
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._set_hot(True))
        self.bind("<Leave>", lambda e: self._set_hot(False))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)

    def _set_hot(self, value):
        self.hot = value
        self.itemconfigure(self._thumb, fill=ACCENT_HOVER if value else "#6255d8")

    def set(self, first, last):
        self.first, self.last = float(first), float(last)
        self._draw()

    def _draw(self):
        h = self.winfo_height()
        if h < 4:
            return
        top, bottom = 8, max(9, h - 8)
        self.coords(self._rail, 7, top, 7, bottom)
        visible = max(0.0, min(1.0, self.last - self.first))
        thumb_h = max(self.MIN_THUMB, (bottom - top) * visible)
        travel = max(0, (bottom - top) - thumb_h)
        y1 = top + travel * max(0.0, min(1.0, self.first))
        self.coords(self._thumb, *round_rect_points(2, y1, 12, y1 + thumb_h, 5))

    def _press(self, event):
        h = self.winfo_height()
        top, bottom = 8, max(9, h - 8)
        visible = max(0.0, min(1.0, self.last - self.first))
        thumb_h = max(self.MIN_THUMB, (bottom - top) * visible)
        travel = max(1, (bottom - top) - thumb_h)
        thumb_top = top + travel * self.first
        if thumb_top <= event.y <= thumb_top + thumb_h:
            self.dragging = True
            self.drag_offset = event.y - thumb_top
        else:
            fraction = max(0.0, min(1.0, (event.y - top - thumb_h / 2) / travel))
            self.command("moveto", fraction)

    def _drag(self, event):
        if not self.dragging:
            return
        h = self.winfo_height()
        top, bottom = 8, max(9, h - 8)
        visible = max(0.0, min(1.0, self.last - self.first))
        thumb_h = max(self.MIN_THUMB, (bottom - top) * visible)
        travel = max(1, (bottom - top) - thumb_h)
        fraction = (event.y - top - self.drag_offset) / travel
        self.command("moveto", max(0.0, min(1.0, fraction)))

    def _release(self, event):
        self.dragging = False


class OptionBox(tk.Canvas):
    """Linha de opção compacta para os menus suspensos personalizados."""
    def __init__(self, parent, text, selected, command, height=38, bg=MENU, icon=None):
        super().__init__(parent, height=height, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self.text, self.selected, self.command = text, selected, command
        self.h, self.bgc, self.icon = height, bg, icon
        self.k = 0.0
        self._bg_item = self._icon_item = self._icon_text_item = None
        self._text_item = self._check_item = None
        self.tw = Tween(self)
        self.bind("<Configure>", self.draw)
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))
        self.bind("<ButtonRelease-1>", self._release)

    def _hover(self, v):
        start = self.k
        target = 1.0 if v else 0.0
        def step(t):
            self.k = start + (target - start) * t
            self.draw()
        self.tw.run(130, step)

    def _release(self, e):
        if 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.h:
            self.command()

    def draw(self, e=None):
        w = self.winfo_width()
        if w < 10:
            return
        hovered = self.k > 0.01
        fill = lerp_color(self.bgc, "#303035", self.k)
        if self.selected:
            fill = lerp_color(fill, "#35343d", 0.45)
        if self._bg_item is None:
            self._bg_item = round_rect(self, 1, 1, w - 1, self.h - 1, 9,
                                       fill=fill, outline="", width=0)
        else:
            self.coords(self._bg_item, *round_rect_points(1, 1, w - 1, self.h - 1, 9))
            self.itemconfigure(self._bg_item, fill=fill)
        text_x = 16
        if self.icon:
            d = 22
            if self._icon_item is None:
                if isinstance(self.icon, tuple):
                    symbol, color = self.icon
                    self._icon_item = self.create_oval(
                        12, (self.h - d) / 2, 12 + d, (self.h + d) / 2,
                        fill=color, outline="")
                    self._icon_text_item = self.create_text(
                        23, self.h / 2, text=symbol, anchor="center", fill="#ffffff",
                        font=(FONT_SEMI, 9 if len(symbol) < 2 else 7))
                else:
                    self._icon_item = self.create_image(23, self.h / 2, image=self.icon,
                                                        anchor="center")
            else:
                if isinstance(self.icon, tuple):
                    symbol, color = self.icon
                    self.itemconfigure(self._icon_item, state="normal", fill=color)
                else:
                    self.itemconfigure(self._icon_item, state="normal", image=self.icon)
            text_x = 44
        if self._text_item is None:
            self._text_item = self.create_text(
                text_x, self.h / 2, text=self.text, anchor="w", fill=TEXT,
                font=(FONT_SEMI if self.selected else FONT, 11))
        else:
            self.coords(self._text_item, text_x, self.h / 2)
            self.itemconfigure(self._text_item, text=self.text, fill=TEXT,
                               font=(FONT_SEMI if self.selected else FONT, 11))
        if self.selected:
            if self._check_item is None:
                self._check_item = self.create_text(
                    w - 18, self.h / 2, text="✓", anchor="center", fill=ACCENT,
                    font=(FONT_SEMI, 10))
            else:
                self.coords(self._check_item, w - 18, self.h / 2)


class DropCard(tk.Canvas):
    """Lista suspensa inteira desenhada em UM canvas. Antes cada opção era uma janela do
    Windows dentro do card: ao abrir/fechar (altura animada) elas se redesenhavam em faixas,
    o que dava o efeito de listras e travadas. Agora só existe um desenho que é recortado.
    O destaque do mouse é uma única 'pílula' que desliza até a opção sob o cursor."""
    PAD, OH, GAP = 6, 38, 2

    def __init__(self, parent, values, current, icons, on_pick, width):
        n = len(values)
        self.H = self.PAD * 2 + n * self.OH + max(0, n - 1) * self.GAP
        super().__init__(parent, bg=BG, highlightthickness=0, bd=0, width=width,
                         height=self.H, cursor="hand2")
        self.values, self.on_pick, self.w = list(values), on_pick, width
        self.hover, self.hl_y, self.hl_k = -1, float(self.PAD), 0.0
        self.tw = Tween(self)
        P, OH = self.PAD, self.OH
        round_rect(self, 1, 1, width - 1, self.H - 1, 16, fill=MENU, outline=BORDER, width=1)
        for i, v in enumerate(self.values):                  # fundo da opção selecionada
            if v == current:
                y = P + i * (OH + self.GAP)
                round_rect(self, P, y, width - P, y + OH, 9,
                           fill=lerp_color(MENU, "#35343d", 0.45), outline="")
        self.hl = round_rect(self, P, P, width - P, P + OH, 9, fill=MENU, outline="")
        for i, v in enumerate(self.values):
            cy = P + i * (OH + self.GAP) + OH / 2
            sel, icon, tx = v == current, icons.get(v), 16
            if icon:
                if isinstance(icon, tuple):
                    symbol, color = icon
                    self.create_oval(12, cy - 11, 34, cy + 11, fill=color, outline="")
                    self.create_text(23, cy, text=symbol, anchor="center", fill="#ffffff",
                                     font=(FONT_SEMI, 9 if len(symbol) < 2 else 7))
                else:
                    self.create_image(23, cy, image=icon, anchor="center")
                tx = 44
            self.create_text(tx, cy, text=v, anchor="w", fill=TEXT,
                             font=(FONT_SEMI if sel else FONT, 11))
            if sel:
                self.create_text(width - 18, cy, text="✓", anchor="center", fill=ACCENT,
                                 font=(FONT_SEMI, 10))
        self.bind("<Motion>", lambda e: self._set_hover(self._row_at(e.y)))
        self.bind("<Leave>", lambda e: self._set_hover(-1))
        self.bind("<ButtonRelease-1>", self._release)

    def _row_at(self, y):
        rel = y - self.PAD
        i = int(rel // (self.OH + self.GAP))
        if 0 <= i < len(self.values) and rel - i * (self.OH + self.GAP) <= self.OH:
            return i
        return -1

    def _set_hover(self, i):
        if i == self.hover:
            return
        self.hover = i
        y0, k0 = self.hl_y, self.hl_k
        if i >= 0:
            y1, k1 = self.PAD + i * (self.OH + self.GAP), 1.0
            if k0 < 0.05:                 # estava apagada: já nasce na linha, sem deslizar de longe
                y0 = y1
        else:
            y1, k1 = y0, 0.0

        def step(t):
            y, k = y0 + (y1 - y0) * t, k0 + (k1 - k0) * t
            self.move(self.hl, 0, y - self.hl_y)
            self.hl_y, self.hl_k = y, k
            self.itemconfigure(self.hl, fill=lerp_color(MENU, "#303035", k))
        self.tw.run(150, step)

    def _release(self, e):
        i = self._row_at(e.y)
        if i >= 0:
            self.on_pick(self.values[i])


class Select(Field):
    """Campo de seleção: ao clicar abre uma lista com cada opção numa caixinha
    arredondada, dentro da própria janela (sem popup). Com editable=True também
    dá pra digitar um valor que não está na lista."""
    def __init__(self, parent, host, values=(), value="", editable=False, on_select=None,
                 option_icons=None):
        var = tk.StringVar(value=value)

        def make_inner(c):
            if editable:
                w = tk.Entry(c, textvariable=var, bg=FIELD, fg=TEXT, insertbackground=TEXT,
                             relief="flat", bd=0, highlightthickness=0, font=(FONT, 11),
                             selectbackground=ACCENT, selectforeground="#ffffff")
            else:
                w = tk.Label(c, textvariable=var, bg=FIELD, fg=TEXT, font=(FONT, 11),
                             anchor="w", cursor="hand2")
                w.bind("<Button-1>", lambda e: self.toggle())
            return w

        super().__init__(parent, make_inner)
        self.var, self.host, self.values = var, host, list(values)
        self.editable, self.on_select = editable, on_select
        self.option_icons = option_icons or {}
        self.is_open, self.card = False, None
        self._H, self._up = 0, False
        self._provider_icon = self._provider_icon_text = self._chev = None
        self.ptw = Tween(self)
        self.configure(cursor="hand2")
        self.bind("<Button-1>", self._click)

    # --- valor ---
    def get(self):
        return self.var.get()

    def set(self, v):
        self.var.set(v)

    def set_values(self, vals):
        self.values = list(vals)

    # --- visual ---
    def draw(self, e=None):
        super().draw(e)
        w = self.winfo_width()
        if w < 10:
            return
        icon = self.option_icons.get(self.get())
        left = 40 if icon else self.r
        self.coords(self.win, left, self.h // 2)
        self.itemconfigure(self.win, width=w - left - self.r - 28)
        if icon:
            if isinstance(icon, tuple):
                symbol, color = icon
                if self._provider_icon is None:
                    self._provider_icon = self.create_oval(
                        12, self.h / 2 - 11, 34, self.h / 2 + 11,
                        fill=color, outline="", tags="provider-icon")
                    self._provider_icon_text = self.create_text(
                        23, self.h / 2, text=symbol, anchor="center", fill="#ffffff",
                        font=(FONT_SEMI, 9 if len(symbol) < 2 else 7), tags="provider-icon")
                else:
                    self.itemconfigure(self._provider_icon, state="normal", fill=color)
                    if self._provider_icon_text is not None:
                        self.itemconfigure(self._provider_icon_text, state="normal", text=symbol,
                                           font=(FONT_SEMI, 9 if len(symbol) < 2 else 7))
            else:
                if self._provider_icon is None:
                    self._provider_icon = self.create_image(23, self.h / 2, image=icon,
                                                            anchor="center", tags="provider-icon")
                else:
                    self.itemconfigure(self._provider_icon, state="normal", image=icon)
                if self._provider_icon_text is not None:
                    self.itemconfigure(self._provider_icon_text, state="hidden")
        elif self._provider_icon is not None:
            self.itemconfigure(self._provider_icon, state="hidden")
            self.itemconfigure(self._provider_icon_text, state="hidden")
        cx, cy = w - self.r - 6, self.h / 2
        d = -2.5 if self.is_open else 2.5   # seta aponta pra cima quando aberto
        if self._chev is None:
            self._chev = self.create_line(
                cx - 5, cy - d, cx, cy + d, cx + 5, cy - d,
                fill=lerp_color(MUTED, TEXT, self.k), width=2,
                capstyle="round", joinstyle="round", tags="chev")
        else:
            self.coords(self._chev, cx - 5, cy - d, cx, cy + d, cx + 5, cy - d)
            self.itemconfigure(self._chev, fill=lerp_color(MUTED, TEXT, self.k))

    def _inner_focused(self):
        try:
            return self.focus_get() is self.inner
        except Exception:
            return False

    # --- abrir / fechar ---
    def _click(self, e):
        if self.editable and e.x < self.winfo_width() - self.r - 36:
            return
        self.toggle()

    def toggle(self):
        if self.is_open:
            self.close()
        else:
            self.open()

    def open(self):
        if self.is_open or not self.values:
            return
        host = self.host
        host.close_dropdown(False)
        host.update_idletasks()
        self.is_open = True
        host._open_dd = self

        w = self.winfo_width()
        pad, oh, gap = 6, 38, 2
        n = len(self.values)
        H = pad * 2 + n * oh + max(0, n - 1) * gap
        x = self.winfo_rootx() - host.winfo_rootx()
        fy = self.winfo_rooty() - host.winfo_rooty()
        y = fy + self.h + 6
        up = y + H > host.winfo_height() - 8
        if up:
            y = fy - H - 6

        card = DropCard(host, self.values, self.get().strip(), self.option_icons, self.pick, w)
        self.card, self._H, self._up = card, H, up

        if up:
            card.place(x=x, y=y, width=w, height=H)
        else:
            card.place(x=x, y=y, width=w, height=1)
            last_h = [1]

            def reveal(t):
                # A altura é inteira no Tk; evita enviar o mesmo configure dezenas de
                # vezes quando o valor interpolado ainda está no mesmo pixel.
                height = max(1, round(H * t))
                if height != last_h[0]:
                    last_h[0] = height
                    try:
                        card.place_configure(height=height)
                    except tk.TclError:
                        self.ptw.stop()

            self.ptw.run(260, reveal, ease=ease_out)
        tk.Misc.tkraise(card)   # Canvas sobrescreve lift/tkraise (viram tag_raise), então chamo o da classe base
        self._focus(True)
        self.draw()

    def pick(self, v):
        self.var.set(v)
        if self.editable:
            try:
                self.inner.icursor("end")
            except tk.TclError:
                pass
        self.close()
        if self.on_select:
            self.on_select(v)

    def close(self, animate=True):
        if not self.is_open:
            return
        self.is_open = False
        if self.host._open_dd is self:
            self.host._open_dd = None
        card, self.card = self.card, None
        self.ptw.stop()
        try:
            self._focus(self.editable and self._inner_focused())
            self.draw()
        except tk.TclError:
            pass
        if card is None:
            return
        if animate and not self._up:
            H = self._H
            last_h = [H]

            def conceal(t):
                height = max(1, round(H * (1 - t)))
                if height != last_h[0]:
                    last_h[0] = height
                    try:
                        card.place_configure(height=height)
                    except tk.TclError:
                        self.ptw.stop()

            self.ptw.run(180, conceal, done=card.destroy, ease=ease_in)
        else:
            try:
                card.destroy()
            except tk.TclError:
                pass


def render_window_icon(kind, color, size, bg=BG, ss=8):
    """Desenha o ícone (minimizar / fechar) em alta resolução e reduz: bordas suaves,
    sem serrilhado, e perfeitamente centralizado no botão. Retorna uma imagem PIL."""
    w, h = size
    k = h / 28
    img = Image.new("RGB", (w * ss, h * ss), bg)
    d = ImageDraw.Draw(img)
    cx, cy = (w / 2 - 0.5) * ss, (h / 2 - 0.5) * ss   # centro de um pixel = traço nítido
    half = 5.0 * k * ss
    lw = 1.4 * k * ss

    def line(x1, y1, x2, y2):
        d.line([(x1, y1), (x2, y2)], fill=color, width=round(lw))
        r = lw / 2                                     # pontas arredondadas
        for x, y in ((x1, y1), (x2, y2)):
            d.ellipse([x - r, y - r, x + r, y + r], fill=color)

    if kind == "min":
        line(cx - half, cy, cx + half, cy)
    else:
        line(cx - half, cy - half, cx + half, cy + half)
        line(cx - half, cy + half, cx + half, cy - half)
    return img.resize((w, h), Image.LANCZOS)


class WinButton(tk.Canvas):
    """Botão da barra de título customizada (minimizar / fechar).
    Sem fundo: ao passar o mouse só a cor do ícone muda, com uma transição suave."""
    HOVER = "#ff5c6a"   # cor do ícone ao passar o mouse (vermelho)
    STEPS = 12          # quadros pré-renderizados da transição de cor

    def __init__(self, parent, kind, command, height=28, width=42):
        super().__init__(parent, width=width, height=height, bg=BG, highlightthickness=0,
                         bd=0, cursor="hand2")
        self.kind, self.command = kind, command
        self.hovering = False
        self.k = 0.0          # 0 = normal, 1 = hover
        self.tw = Tween(self)
        # ícones PNG gerados em memória (nada para empacotar junto do .exe)
        self.frames = [
            ImageTk.PhotoImage(render_window_icon(
                kind, lerp_color(MUTED, self.HOVER, i / self.STEPS), (width, height)))
            for i in range(self.STEPS + 1)
        ]
        self.item = self.create_image(0, 0, anchor="nw", image=self.frames[0])
        self.bind("<Enter>", lambda e: self._set(True))
        self.bind("<Leave>", lambda e: self._set(False))
        self.bind("<ButtonRelease-1>", self._release)

    def _set(self, v):
        self.hovering = v
        start, target = self.k, 1.0 if v else 0.0
        def step(t):
            self.k = start + (target - start) * t
            self.itemconfigure(self.item, image=self.frames[round(self.k * self.STEPS)])
        self.tw.run(180, step)

    def _release(self, e):
        if self.hovering:
            self.command()


def render_toast(W, H, bg, fg, kind, ss=4):
    """Fundo do aviso: retângulo bem arredondado, borda fina e ícone, desenhados em alta
    resolução e reduzidos (bordas suaves, sem serrilhado)."""
    img = Image.new("RGB", (W * ss, H * ss), BG)
    d = ImageDraw.Draw(img)
    r = 16
    d.rounded_rectangle([0, 0, W * ss - 1, H * ss - 1], radius=r * ss,
                        fill=lerp_color(bg, fg, 0.38))
    d.rounded_rectangle([ss, ss, W * ss - 1 - ss, H * ss - 1 - ss], radius=(r - 1) * ss, fill=bg)
    cx, cy = 30 * ss, ((H - 12) / 2) * ss
    R = 13 * ss
    d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=lerp_color(bg, fg, 0.20))
    lw = round(2.2 * ss)

    def line(pts):
        d.line([(cx + x * ss, cy + y * ss) for x, y in pts], fill=fg, width=lw, joint="curve")
        rr = lw / 2
        for x, y in (pts[0], pts[-1]):
            d.ellipse([cx + x * ss - rr, cy + y * ss - rr, cx + x * ss + rr, cy + y * ss + rr],
                      fill=fg)

    def dot(x, y, rad):
        d.ellipse([cx + (x - rad) * ss, cy + (y - rad) * ss,
                   cx + (x + rad) * ss, cy + (y + rad) * ss], fill=fg)

    if kind == "ok":
        line([(-5, 0.5), (-1.5, 4), (5.5, -3.5)])
    elif kind == "error":
        line([(-4.2, -4.2), (4.2, 4.2)])
        line([(-4.2, 4.2), (4.2, -4.2)])
    elif kind == "warn":
        line([(0, -6), (0, 1.5)])
        dot(0, 5.6, 1.5)
    else:
        dot(0, -5.6, 1.5)
        line([(0, -1.5), (0, 6)])
    return img.resize((W, H), Image.LANCZOS)


class Toast(tk.Canvas):
    """Aviso moderno: cartão arredondado com ícone, texto e uma barrinha de tempo.
    Entra subindo com fade, a barra mostra quanto falta, passar o mouse pausa o tempo,
    clicar fecha. É um único widget (um Canvas), então anima leve."""
    STEPS = 8          # quadros pré-renderizados do fade
    DURATION = 6500    # ms visível
    REST = 24          # folga da borda de baixo da janela
    RISE = 30          # quanto sobe ao entrar

    def __init__(self, app):
        super().__init__(app, bg=BG, highlightthickness=0, bd=0, cursor="hand2")
        self.app = app
        self.state = "hidden"      # hidden | in | shown | out
        self.e = 0.0               # 0 = invisível, 1 = totalmente visível
        self.left = 1.0            # fração do tempo que ainda resta
        self.frames, self.W, self.H = [], 0, 0
        self.tw, self.timer = Tween(self), Tween(self)
        self.bind("<Button-1>", lambda e: self.hide())
        self.bind("<Enter>", lambda e: self._pause())
        self.bind("<Leave>", lambda e: self._resume())

    def _build(self, text, bg, fg, kind):
        W = max(260, min(440, self.app._win[0] - 48))
        tx = 60
        text_w = W - tx - 22
        self.delete("all")
        probe = self.create_text(0, 0, text=text, font=(FONT, 10), width=text_w, anchor="nw")
        x1, y1, x2, y2 = self.bbox(probe)
        self.delete(probe)
        H = max(58, (y2 - y1) + 38)
        self.W, self.H = W, H
        self.configure(width=W, height=H)
        base = render_toast(W, H, bg, fg, kind)
        solid = Image.new("RGB", base.size, BG)
        self.frames = [ImageTk.PhotoImage(Image.blend(solid, base, i / (self.STEPS - 1)))
                       for i in range(self.STEPS)]
        self._img = self.create_image(0, 0, anchor="nw", image=self.frames[0])
        self._txt = self.create_text(tx, (H - 12) / 2, text=text, font=(FONT, 10),
                                     width=text_w, anchor="w", justify="left", fill=BG)
        self._by = H - 13
        self._c_track, self._c_bar = lerp_color(bg, fg, 0.18), lerp_color(bg, fg, 0.85)
        self._track = self.create_line(22, self._by, W - 22, self._by, width=3,
                                       capstyle="round", fill=BG)
        self._bar = self.create_line(22, self._by, W - 22, self._by, width=3,
                                     capstyle="round", fill=BG)

    def _apply(self, e, rise=None):
        """Desenha o aviso no ponto 'e' da entrada (0 = escondido, 1 = pronto)."""
        self.e = e
        f = min(1.0, e * 1.4)                     # o fade termina um pouco antes da subida
        self.itemconfigure(self._img, image=self.frames[round(f * (self.STEPS - 1))])
        self.itemconfigure(self._txt, fill=lerp_color(BG, TEXT, f))
        self.itemconfigure(self._track, fill=lerp_color(BG, self._c_track, f))
        self.itemconfigure(self._bar, fill=lerp_color(BG, self._c_bar, f))
        off = rise if rise is not None else self.RISE * (1 - e)
        place_args = dict(relx=0.5, rely=1.0, anchor="s", width=self.W, height=self.H,
                          y=int(-self.REST + off))
        if self.winfo_manager() == "place":
            self.place_configure(**place_args)
        else:
            self.place(**place_args)

    def _set_bar(self):
        self.coords(self._bar, 22, self._by, 22 + (self.W - 44) * max(self.left, 0.001), self._by)

    def show(self, text, kind="info"):
        bg, fg = TOAST_COLORS.get(kind, TOAST_COLORS["info"])
        was_in = self.state in ("in", "shown")
        self.tw.stop()
        self.timer.stop()
        self._build(text, bg, fg, kind)
        self.left = 1.0
        self._set_bar()
        self.state = "in"
        tk.Misc.tkraise(self)
        if was_in:
            # já estava na tela: troca o conteúdo com um pequeno pulinho
            self.tw.run(260, lambda t: self._apply(1.0, rise=10 * (1 - t)), done=self._shown)
        else:
            self.tw.run(420, self._apply, done=self._shown)

    def _shown(self):
        self.state = "shown"
        self._run_timer()

    def _run_timer(self):
        if self.left <= 0.001:
            self.hide()
            return
        start = self.left

        def step(t):
            self.left = start * (1 - t)
            self._set_bar()
        self.timer.run(start * self.DURATION, step, done=self.hide, ease=linear)

    def _pause(self):
        if self.state == "shown":
            self.timer.stop()

    def _resume(self):
        if self.state == "shown":
            self._run_timer()

    def hide(self):
        if self.state in ("hidden", "out"):
            return
        self.timer.stop()
        self.tw.stop()
        self.state = "out"
        e0 = self.e

        def finish():
            self.state = "hidden"
            self.place_forget()
        self.tw.run(260, lambda t: self._apply(e0 * (1 - t)), done=finish, ease=ease_in)


class App(tk.Tk):
    LOGIN_SIZE = (440, 575)   # login / criar conta (a altura ainda se ajusta ao conteúdo, ver _fit_begin)
    FOOTER = 48               # faixa livre embaixo para a versão
    COL_SHIFT = 14            # a coluna central sobe um pouco para sobrar espaço embaixo
    REGISTER_SIZE = (440, 640)   # criar conta (tem o campo da chave de licença)
    DASH_SIZE = (500, 620)    # painel principal
    SETTINGS_SIZE = (520, 680)   # configurações
    SETTINGS_TOP = 36            # Configurações: coluna presa no topo (ver make_settings)

    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        # abre no centro da tela com o tamanho compacto do login (encolhe se a tela for pequena)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(self.LOGIN_SIZE[0], sw - 40), min(self.LOGIN_SIZE[1], sh - 80)
        self._win = self._cur = (w, h)      # tamanho final / tamanho atual (durante a animação)
        global CLOCK
        CLOCK = Clock(self)
        self._fit_tw = Tween(self)
        self._screen_tw = Tween(self)
        self._window_fx_tw = Tween(self)
        self._shake_tw, self._shake_base, self._err_fields = Tween(self), (0, 0), ()
        self._grow_active, self._grow_queue, self._fit_start_job = False, [], None
        self._fit_reserve = 0   # altura extra que a tela pode ganhar sem a janela mudar (Configurações)
        self._dot_cache, self._copy_job = {}, None
        self._transition_generation = 0
        self._has_shown_screen = False
        self._use_screen_fade = False
        self._screen_finish_job = None
        self._closing = False
        self._minimizing = False
        self._restore_geometry = None
        self._settings_viewport = None
        self._region_api = None
        self._region_size = None
        self.lic, self._license_job = LicenseClient(), None
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
        self.minsize(w, h)
        self.configure(bg=BG)
        self.cfg = config()
        self.busy = False
        self.loading = False
        self.user = None
        self.col = None
        self.screen = "login"
        self.view = {"status": "Pronto", "mod": "Módulo: —", "ex": "Exercício: —", "ans": "—"}
        self._open_dd = None

        self.logo_imgs = load_logo_images()
        self.provider_icon_imgs = load_provider_icons()
        self._apply_logo_icon()

        self.setup_style()
        self.body = tk.Frame(self, bg=BG)
        self.body.pack(fill="both", expand=True)
        # versão: fica na janela (não dentro das telas), criada uma vez e acima do conteúdo,
        # com folga da borda de baixo para nunca ser cortada
        self.version = tk.Label(self, text=f"v{APP_VERSION}", bg=BG, fg="#4a4a5a",
                                font=(FONT, 8), padx=4, pady=2)
        self.version.place(relx=0.5, rely=1.0, anchor="s", y=-14)
        self.toast = Toast(self)
        self.bind_all("<Button-1>", self._global_click, add="+")
        self.bind_all("<Escape>", lambda e: self.close_dropdown())
        self.bind_all("<MouseWheel>", self._scroll_settings, add="+")

        self.make_login()
        threading.Thread(target=self.lic.warm, daemon=True).start()   # abre a sessão com o servidor
        self.listener = keyboard.Listener(on_press=self.hotkey)
        self.listener.daemon = True
        self.listener.start()

        # tira a faixa branca padrão do Windows e usa a barra própria (minimizar / fechar)
        try:
            self.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        # Janela personalizada: mantém os cantos arredondados e os controles
        # independentes de minimizar/fechar.
        if os.name == "nt" and self.strip_native_titlebar():
            self.build_titlebar()

        # a janela inteira aparece em fade ao abrir
        try:
            self.attributes("-alpha", 0.0)
            def fade_step(t):
                self.attributes("-alpha", t)
            Tween(self).run(380, fade_step, done=self._fade_done)
        except tk.TclError:
            pass

    # ----- barra de título própria -----
    _borderless = False

    def _apply_logo_icon(self):
        """Aplica as várias resoluções da logo ao ícone nativo da janela."""
        if self.logo_imgs:
            try:
                self.iconphoto(True, *self.logo_imgs)
            except (tk.TclError, TypeError):
                pass

    def _user32(self):
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        u.GetParent.restype = wintypes.HWND
        u.GetParent.argtypes = [wintypes.HWND]
        u.GetWindowLongW.restype = ctypes.c_long
        u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        u.SetWindowLongW.restype = ctypes.c_long
        u.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        return u

    def _hwnd(self, u):
        return u.GetParent(self.winfo_id()) or self.winfo_id()

    def strip_native_titlebar(self):
        """Janela sem borda nenhuma (sem faixa branca). Usa overrideredirect e devolve o
        ícone na barra de tarefas via WS_EX_APPWINDOW. Retorna True se deu certo."""
        try:
            self.overrideredirect(True)
            self.update_idletasks()
            u = self._user32()
            hwnd = self._hwnd(u)
            GWL_EXSTYLE, WS_EX_TOOLWINDOW, WS_EX_APPWINDOW = -20, 0x00000080, 0x00040000
            ex = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
            u.SetWindowLongW(hwnd, GWL_EXSTYLE, (ex & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW)
            self._borderless = True
            # esconde e mostra de novo para o Windows registrar o botão na barra de tarefas
            self.withdraw()
            self.after(30, self._show_borderless)
            return True
        except Exception:
            self._borderless = False
            try:
                self.overrideredirect(False)
            except Exception:
                pass
            return False

    CORNER_RADIUS = 18

    _native_round = False

    def round_corners(self, w=None, h=None):
        """Cantos arredondados. Windows 11: arredondamento nativo (suave) + borda fina.
        Windows 10: recorta a janela com uma região arredondada."""
        try:
            import ctypes
            from ctypes import wintypes
            u = self._user32()
            hwnd = self._hwnd(u)
            dwm = ctypes.windll.dwmapi
            dwm.DwmSetWindowAttribute.restype = ctypes.c_long
            dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD,
                                                  ctypes.c_void_p, wintypes.DWORD]
            pref = ctypes.c_int(2)  # DWMWCP_ROUND
            if dwm.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref)) == 0:
                r, g, b = (int(BORDER[i:i + 2], 16) for i in (1, 3, 5))
                col = ctypes.c_uint(r | (g << 8) | (b << 16))
                dwm.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(col), ctypes.sizeof(col))
                self._native_round = True
                return
            self._native_round = False
            gdi = ctypes.windll.gdi32
            gdi.CreateRoundRectRgn.restype = wintypes.HRGN
            gdi.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
            u.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN, wintypes.BOOL]
            d = self.CORNER_RADIUS * 2
            rgn = gdi.CreateRoundRectRgn(0, 0, (w or self.winfo_width()) + 1,
                                         (h or self.winfo_height()) + 1, d, d)
            u.SetWindowRgn(hwnd, rgn, True)
        except Exception:
            pass

    def _apply_region(self, w, h):
        """Mantém os cantos arredondados durante o resize no Windows 10.

        As referências ctypes são preparadas uma única vez. O tamanho ainda precisa ser
        atualizado por quadro no Windows 10, mas sem repetir imports, descoberta do HWND
        e configuração de assinaturas, que eram parte importante do stutter original.
        """
        try:
            import ctypes
            from ctypes import wintypes
            if self._region_size == (w, h):
                return
            if self._region_api is None:
                u = self._user32()
                gdi = ctypes.windll.gdi32
                gdi.CreateRoundRectRgn.restype = wintypes.HRGN
                gdi.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
                u.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN, wintypes.BOOL]
                self._region_api = (u, self._hwnd(u), gdi.CreateRoundRectRgn, u.SetWindowRgn)
            u, hwnd, create_region, set_region = self._region_api
            d = self.CORNER_RADIUS * 2
            set_region(hwnd, create_region(0, 0, w + 1, h + 1, d, d), True)
            self._region_size = (w, h)
        except Exception:
            pass

    def _clear_region(self):
        """Remove o recorte antigo durante o resize; ele volta no último quadro."""
        try:
            if self._region_api is None:
                self._apply_region(self.winfo_width(), self.winfo_height())
            if self._region_api is not None:
                _, hwnd, _, set_region = self._region_api
                set_region(hwnd, 0, True)
            self._region_size = None
        except Exception:
            pass

    def _fade_done(self):
        """Fim do fade de abertura: volta a janela ao modo normal (sem camada alfa do
        Windows), que redimensiona bem mais leve que uma janela 'layered'."""
        try:
            self.attributes("-alpha", 1.0)
        except tk.TclError:
            return
        if os.name != "nt" or not self._borderless:
            return
        try:
            import ctypes
            from ctypes import wintypes
            u = self._user32()
            hwnd = self._hwnd(u)
            GWL_EXSTYLE, WS_EX_LAYERED = -20, 0x00080000
            ex = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if ex & WS_EX_LAYERED:
                u.SetWindowLongW(hwnd, GWL_EXSTYLE, ex & ~WS_EX_LAYERED)
                u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                           ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                           wintypes.UINT]
                # NOMOVE | NOSIZE | NOZORDER | NOACTIVATE | FRAMECHANGED
                u.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)
        except Exception:
            pass

    def _show_borderless(self):
        tk.Tk.deiconify(self)
        self.update_idletasks()
        self._apply_logo_icon()
        self.round_corners()
        try:
            self.focus_force()
        except tk.TclError:
            pass

    # Com overrideredirect o iconify/deiconify do Tk não funciona; troco por ShowWindow.
    def iconify(self):
        if not self._borderless:
            return super().iconify()
        u = self._user32()
        u.ShowWindow(self._hwnd(u), 6)   # SW_MINIMIZE

    def deiconify(self):
        if not self._borderless:
            return super().deiconify()
        u = self._user32()
        u.ShowWindow(self._hwnd(u), 9)   # SW_RESTORE
        try:
            tk.Tk.deiconify(self)
        except tk.TclError:
            pass

    def _fade_restore(self):
        """Entrada suave ao restaurar a janela pela barra de tarefas."""
        self._window_fx_tw.stop()
        self._window_fx_tw.run(
            160,
            lambda t: self.attributes("-alpha", t),
            done=lambda: self.attributes("-alpha", 1.0),
            ease=ease_out,
        )

    def close_app(self):
        """Fecha a janela depois de uma saída visual curta, sem encerrar abruptamente."""
        if self._closing:
            return
        self._closing = True
        self._minimizing = False
        self._window_fx_tw.stop()
        self._screen_tw.stop()
        self._fit_tw.stop()

        def done():
            try:
                self._stop_license_watch()
                if getattr(self, "listener", None):
                    self.listener.stop()
            except Exception:
                pass
            self.destroy()

        try:
            self._window_fx_tw.run(
                180,
                lambda t: self.attributes("-alpha", 1.0 - t),
                done=done,
                ease=ease_in,
            )
        except tk.TclError:
            done()

    def build_titlebar(self):
        bar = tk.Frame(self, bg=BG, height=36)
        bar.pack(side="top", fill="x", before=self.body)
        bar.pack_propagate(False)
        brand = tk.Frame(bar, bg=BG, cursor="arrow")
        brand.pack(side="left", padx=(16, 0), pady=(8, 0))
        tk.Frame(brand, bg=ACCENT, width=5, height=14).pack(side="left", padx=(0, 8))
        tk.Label(brand, text=APP_NAME, bg=BG, fg="#b9b5d8",
                 font=(FONT_SEMI, 9)).pack(side="left")
        tk.Label(brand, text=f"  v{APP_VERSION}", bg=BG, fg="#505064",
                 font=(FONT, 8)).pack(side="left")
        # botões independentes, com folga das bordas arredondadas da janela
        WinButton(bar, "close", self.destroy).pack(side="right", anchor="n", padx=(4, 14), pady=(8, 0))
        WinButton(bar, "min", self.iconify).pack(side="right", anchor="n", pady=(8, 0))
        for widget in (bar, brand, *brand.winfo_children()):
            widget.bind("<ButtonPress-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_move)
        self.titlebar = bar

    def _drag_start(self, e):
        self._drag_off = (e.x_root - self.winfo_x(), e.y_root - self.winfo_y())

    def _drag_move(self, e):
        ox, oy = self._drag_off
        self.geometry(f"+{e.x_root - ox}+{e.y_root - oy}")

    def _taskbar_target(self, x, y, w, h):
        """Calcula um ponto de destino visual próximo à barra de tarefas do Windows."""
        if os.name != "nt":
            return x + w // 2, y + h // 2
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
            user32.FindWindowW.restype = wintypes.HWND
            user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
            hwnd = user32.FindWindowW("Shell_TrayWnd", None)
            rect = wintypes.RECT()
            if not hwnd or not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                raise OSError
            tw, th = rect.right - rect.left, rect.bottom - rect.top
            # A taskbar horizontal costuma ser inferior/superior; barras verticais
            # ficam à esquerda/direita. O centro da janela mantém a trajetória natural.
            if tw >= th:
                tx = x + w // 2
                ty = rect.top + 6 if rect.top < y else rect.bottom - 6
            else:
                tx = rect.left + 6 if rect.left < x else rect.right - 6
                ty = y + h // 2
            return tx, ty
        except Exception:
            return x + w // 2, y + h // 2

    def fit(self, size):
        """Prepara uma troca de tela sem animar a geometria nativa do Windows.

        Redimensionar uma janela borderless por quadro deixa o Window Manager recalcular
        região, minsize e layout em momentos diferentes. O resultado parece um teleport
        mesmo quando os valores do código estão corretos. A nova estratégia posiciona a
        janela diretamente no tamanho final, mantém o conteúdo oculto durante o layout e
        revela a tela com um fade curto e determinístico.
        """
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(size[0], sw - 40), min(size[1], sh - 80)
        self._want = (w, h)
        self._grow_active = True
        self._use_screen_fade = self._has_shown_screen
        self._fit_tw.stop()
        self._screen_tw.stop()
        if self._screen_finish_job:
            try:
                self.after_cancel(self._screen_finish_job)
            except tk.TclError:
                pass
            self._screen_finish_job = None
        if self._use_screen_fade:
            try:
                self.attributes("-alpha", 0.0)
            except tk.TclError:
                self._use_screen_fade = False
        if self._fit_start_job:
            self.after_cancel(self._fit_start_job)
        self._fit_start_job = self.after(1, self._fit_begin)

    def _after_grow(self, fn):
        """Executa fn quando a janela terminar de crescer (ou já, se não está crescendo)."""
        generation = self._transition_generation
        if self._grow_active:
            self._grow_queue.append(fn)
        else:
            # mesmo sem crescimento, dá uns quadros pro Tk processar os <Configure> e os
            # Canvas se desenharem ANTES de a tela aparecer (senão entram vazios)
            def later():
                if generation != self._transition_generation:
                    return
                try:
                    fn()
                except tk.TclError:
                    pass
            self.after(48, later)

    def _flush_grow(self):
        self._grow_active = False
        queue, self._grow_queue = self._grow_queue, []
        for fn in queue:
            try:
                fn()
            except tk.TclError:
                pass

    def _fit_begin(self):
        self._fit_start_job = None
        w, h = self._want
        try:
            self.update_idletasks()      # mede a tela nova já completamente construída
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            # altura pelo conteúdo real: com outra fonte/escala do Windows a coluna pode ser
            # maior que o tamanho pré-definido e encostaria na versão. Garante espaço.
            col = self.col
            if col is not None:
                tb = self.titlebar.winfo_reqheight() if hasattr(self, "titlebar") else 0
                if getattr(col, "_top", None) is None:
                    need = col.winfo_reqheight() + 2 * (self.FOOTER - self.COL_SHIFT) + tb
                else:   # presa ao topo: topo + conteúdo (+ o que ainda pode aparecer) + rodapé
                    need = col._top + col.winfo_reqheight() + self._fit_reserve + self.FOOTER + tb
                h = min(max(h, need), sh - 80)
            self._win = (w, h)
            ow, oh = self._cur
            sx, sy = self.winfo_x(), self.winfo_y()
            # O canto superior esquerdo é a âncora da transição. Assim, somente a
            # lateral direita e a borda inferior se deslocam; recentralizar aqui fazia
            # a janela parecer teleportar quando o tamanho final era aplicado.
            ex, ey = sx, sy
            self.minsize(1, 1)
        except tk.TclError:
            self._flush_grow()
            return

        def step(t):
            cw = round(ow + (w - ow) * t)
            ch = round(oh + (h - oh) * t)
            self.geometry(f"{cw}x{ch}+{sx}+{sy}")
            self._cur = (cw, ch)
            if self._borderless and not self._native_round:
                self._apply_region(cw, ch)

        def done():
            self._cur = (w, h)
            self.minsize(w, h)
            # O conteúdo continua fora da área visível até este callback terminar.
            self._screen_finish_job = self.after(16, self._finish_screen_transition)

        if (w, h) == (ow, oh) and (sx, sy) == (ex, ey):
            done()
        else:
            self._fit_tw.run(320, step, done=done, ease=ease_in_out)

    def _finish_screen_transition(self):
        """Revela a tela já estabilizada e executa o fade de entrada."""
        self._screen_finish_job = None
        self._flush_grow()
        self._has_shown_screen = True
        if not self._use_screen_fade:
            return

        def step(t):
            try:
                self.attributes("-alpha", t)
            except tk.TclError:
                self._screen_tw.stop()

        def done():
            try:
                self.attributes("-alpha", 1.0)
            except tk.TclError:
                pass
            self._use_screen_fade = False

        self._screen_tw.run(180, step, done=done, ease=ease_out)

    # ----- estilo / utilidades -----
    def setup_style(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure("Dark.TCombobox", fieldbackground=FIELD, background=FIELD, foreground=TEXT,
                     bordercolor=FIELD, lightcolor=FIELD, darkcolor=FIELD, arrowcolor=MUTED,
                     borderwidth=0, padding=2, selectbackground=FIELD, selectforeground=TEXT,
                     insertcolor=TEXT)
        st.map("Dark.TCombobox",
               fieldbackground=[("readonly", FIELD), ("focus", FIELD)],
               foreground=[("readonly", TEXT)],
               selectbackground=[("readonly", FIELD)],
               selectforeground=[("readonly", TEXT)],
               background=[("active", FIELD)],
               arrowcolor=[("active", TEXT)])
        self.option_add("*TCombobox*Listbox.background", FIELD)
        self.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

    def clear(self):
        self.close_dropdown(False)
        self._settings_viewport = None
        self._transition_generation += 1
        if self._fit_start_job:
            try:
                self.after_cancel(self._fit_start_job)
            except tk.TclError:
                pass
        self._fit_start_job = None
        self._fit_tw.stop()
        self._screen_tw.stop()
        if self._screen_finish_job:
            try:
                self.after_cancel(self._screen_finish_job)
            except tk.TclError:
                pass
        self._screen_finish_job = None
        self._grow_active = False
        self._grow_queue.clear()
        self._fit_reserve = 0
        for w in self.body.winfo_children():
            w.destroy()

    def _scroll_settings(self, event):
        """Rola a tela compacta sem interferir nos outros painéis."""
        viewport = self._settings_viewport
        if viewport is None or self.screen != "settings":
            return
        try:
            widget = str(event.widget)
            if widget == str(viewport) or widget.startswith(str(self.col)):
                viewport.yview_scroll(-1 if event.delta > 0 else 1, "units")
        except tk.TclError:
            pass

    def close_dropdown(self, animate=True):
        dd = self._open_dd
        if dd is not None:
            dd.close(animate)

    def _global_click(self, e):
        """Clicou fora da lista aberta: fecha."""
        dd = self._open_dd
        if dd is None:
            return
        wp = str(e.widget)
        for p in (str(dd), str(dd.card) if dd.card is not None else None):
            if p and (wp == p or wp.startswith(p + ".")):
                return
        dd.close()

    def new_col(self, width, dy=28, top=None, scroll=False):
        """Coluna central da tela. É montada FORA da área visível (x=-5000): os widgets são
        criados, medidos e desenhados escondidos, enquanto a janela cresce. Quando tudo está
        pronto ela é revelada de uma vez, já completa. Não deslizo mais a coluna: cada widget
        é uma janela nativa do Windows e mover ~25 ao mesmo tempo gera quadros pela metade."""
        viewport = scrollbar = None
        if scroll:
            viewport = tk.Canvas(self.body, bg=BG, highlightthickness=0, bd=0)
            viewport.place(relx=0.5, rely=0.0, anchor="n", width=width, relheight=1.0,
                           height=-(top or 0) - 34, x=-5000, y=top or 0)
            scrollbar = SmoothScrollbar(self.body, command=None)
            scrollbar.place(relx=0.5, rely=0.0, anchor="n", x=-5000, y=top or 0,
                            relheight=1.0, height=-(top or 0) - 34)
            scrollbar.command = viewport.yview
            viewport.configure(yscrollcommand=scrollbar.set)
            col = tk.Frame(viewport, bg=BG)
            inner_window = viewport.create_window(width // 2, 0, window=col,
                                                  anchor="n", width=max(1, width - 12))

            def sync_scrollregion(_=None):
                try:
                    viewport.itemconfigure(inner_window, width=max(1, viewport.winfo_width() - 12))
                    viewport.configure(scrollregion=viewport.bbox("all"))
                except tk.TclError:
                    pass

            viewport.bind("<Configure>", sync_scrollregion)
            col.bind("<Configure>", sync_scrollregion)
            col._viewport = viewport
            col._scrollbar = scrollbar
            self._settings_viewport = viewport
        else:
            col = tk.Frame(self.body, bg=BG)
        col._top = top
        if not scroll:
            if top is None:
                col.place(relx=0.5, rely=0.5, anchor="center", width=width, x=-5000, y=-self.COL_SHIFT)
            else:
                # presa ao topo: quando um bloco aparece/some no meio da tela, só o que está
                # ABAIXO dele se mexe (o que está acima, e a lista aberta, ficam parados)
                col.place(relx=0.5, rely=0.0, anchor="n", width=width, x=-5000, y=top)
        col._shown = False
        self.col = col
        generation = self._transition_generation

        def show():
            if generation != self._transition_generation:
                return
            if scroll:
                viewport.place_configure(x=0)
                scrollbar.place_configure(x=width // 2 + 5)
            else:
                col.place_configure(x=0)
            col._shown = True
        self._after_grow(show)
        return col

    def shake(self, fields=None):
        """Feedback de erro: a JANELA balança (um único movimento que o Windows compõe sem
        redesenhar nada dentro, então fica fluido) e a borda dos campos pisca em vermelho."""
        if fields is None:
            fields = getattr(self, "_err_fields", ()) if self.screen in ("login", "register") else ()
        for f in fields:
            try:
                f.flash()
            except tk.TclError:
                pass
        if self._grow_active:        # janela ainda mudando de tamanho: só o piscar
            return
        if self._shake_tw._run is None:
            self._shake_base = (self.winfo_x(), self.winfo_y())
        x0, y0 = self._shake_base
        amp = 10

        def step(t):
            dx = round(math.sin(t * math.pi * 7) * (1 - t) ** 2 * amp)   # oscila e amortece
            self.geometry(f"+{x0 + dx}+{y0}")

        def done():
            self.geometry(f"+{x0}+{y0}")
        self._shake_tw.run(520, step, done=done, ease=linear)

    def lbl(self, parent, text, pady=(16, 6)):
        l = tk.Label(parent, text=text, bg=BG, fg=MUTED, font=(FONT, 10), anchor="w")
        l.pack(fill="x", pady=pady)
        return l

    def section(self, parent, text, pady=(14, 5)):
        """Título discreto de seção para dar hierarquia sem adicionar outro card."""
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=pady)
        tk.Frame(row, bg=ACCENT, width=3, height=14).pack(side="left", padx=(0, 8))
        tk.Label(row, text=text.upper(), bg=BG, fg="#b7b3d6",
                 font=(FONT_SEMI, 8), anchor="w").pack(side="left")
        tk.Frame(row, bg=BORDER, height=1).pack(side="left", fill="x", expand=True, padx=(12, 0))
        return row

    def entry(self, parent, show=""):
        return tk.Entry(parent, show=show, bg=FIELD, fg=TEXT, insertbackground=TEXT,
                        relief="flat", bd=0, highlightthickness=0, font=(FONT, 12),
                        selectbackground=ACCENT, selectforeground="#ffffff")

    def heading(self, parent, text, font):
        """Título com fade-in e um tracinho roxo que cresce."""
        lab = tk.Label(parent, text=text, bg=BG, fg=BG, font=font)
        lab.pack()
        line = tk.Frame(parent, bg=ACCENT, height=2, width=1)
        line.pack(pady=(14, 0))
        def go():
            Tween(lab).run(650, lambda t: lab.config(fg=lerp_color(BG, TEXT, t)))
            Tween(line).run(550, lambda t: line.config(width=max(1, int(38 * t))))
        self._after_grow(go)

    def wordmark(self, parent, size):
        self.heading(parent, spaced(APP_NAME), (FONT_LIGHT, size))

    # ----- avisos dentro da janela (sem popups) -----
    def notify(self, text, kind="info"):
        self.toast.show(text, kind)

    def hide_banner(self):
        self.toast.hide()

    # ----- telas -----
    def make_login(self, prefill=""):
        self.clear()
        self.fit(self.LOGIN_SIZE)
        prefill = prefill or self.cfg.get("remember_user", "")
        self.screen = "login"
        col = self.new_col(380)

        self.wordmark(col, 26)
        tk.Label(col, text="Entre para continuar", bg=BG, fg=MUTED,
                 font=(FONT, 11)).pack(pady=(12, 18))

        self.lbl(col, "Usuário")
        uf = Field(col, lambda c: self.entry(c)); uf.pack(fill="x")
        self.u = uf.inner
        uf_login = uf
        self.lbl(col, "Senha")
        pf = Field(col, lambda c: self.entry(c, show="•")); pf.pack(fill="x")
        self.p = pf.inner
        self._err_fields = (uf_login, pf)
        pf.attach_right(EyeToggle(pf, self.p), 26)    # mesmo olho da tela de API Key

        opts = tk.Frame(col, bg=BG)
        opts.pack(fill="x", pady=(8, 0))
        self.remember = Check(opts, "Lembrar usuário", checked=bool(self.cfg.get("remember_user")))
        self.remember.pack(side="left")

        self.login_btn = RoundButton(col, "Entrar", self.do_login)
        self.login_btn.pack(fill="x", pady=(18, 10))
        RoundButton(col, "Criar conta", self.make_register, style="secondary").pack(fill="x")

        self.u.bind("<Return>", lambda e: self.p.focus_set())
        self.p.bind("<Return>", lambda e: self.do_login())
        if prefill:
            self.u.insert(0, prefill)
            self.p.focus_set()
        else:
            self.u.focus_set()

    def make_register(self):
        self.clear()
        self.fit(self.REGISTER_SIZE)
        self.screen = "register"
        col = self.new_col(380)

        self.wordmark(col, 26)
        tk.Label(col, text="Criar conta", bg=BG, fg=TEXT, font=(FONT_LIGHT, 18)).pack(pady=(22, 2))
        tk.Label(col, text="Use a chave de licença que você recebeu", bg=BG, fg=MUTED,
                 font=(FONT, 10)).pack(pady=(0, 6))

        self.lbl(col, "Usuário")
        uf = Field(col, lambda c: self.entry(c)); uf.pack(fill="x")
        self.ru = uf.inner
        uf_reg = uf
        self.lbl(col, "Senha")
        pf = Field(col, lambda c: self.entry(c, show="•")); pf.pack(fill="x")
        self.rp = pf.inner
        pf.attach_right(EyeToggle(pf, self.rp), 26)
        self.lbl(col, "Chave de licença")
        kf = Field(col, lambda c: self.entry(c)); kf.pack(fill="x")
        self.rk = kf.inner
        self._err_fields = (uf_reg, pf, kf)

        self.reg_btn = RoundButton(col, "Criar conta", self.do_register)
        self.reg_btn.pack(fill="x", pady=(24, 10))
        RoundButton(col, "Voltar", self.make_login, style="secondary").pack(fill="x")

        self.ru.bind("<Return>", lambda e: self.rp.focus_set())
        self.rp.bind("<Return>", lambda e: self.rk.focus_set())
        self.rk.bind("<Return>", lambda e: self.do_register())
        self.ru.focus_set()

    def _btn_text(self, btn, text):
        try:
            btn.text = text
            btn.draw()
        except (tk.TclError, AttributeError):
            pass

    def do_register(self):
        if getattr(self, "_reg_busy", False):
            return
        name, pwd, key = self.ru.get().strip(), self.rp.get(), self.rk.get().strip()
        try:
            if len(name) < 3:
                raise ValueError("Usuário: mínimo 3 caracteres.")
            if len(pwd) < 6:
                raise ValueError("Senha: mínimo 6 caracteres.")
            if not key:
                raise ValueError("Informe a chave de licença.")
        except ValueError as e:
            self.notify(str(e), "error")
            self.shake()
            return
        self._reg_busy = True
        self._btn_text(self.reg_btn, "Criando…")

        def work():
            try:
                self.lic.register(name, pwd, key)
                res = ("ok", "")
            except LicenseError as e:
                res = ("error", str(e))
            except Exception:
                res = ("error", "Não foi possível criar a conta. Tente de novo.")
            self.after(0, lambda: self._register_done(res, name))
        threading.Thread(target=work, daemon=True).start()

    def _register_done(self, res, name):
        self._reg_busy = False
        if self.screen != "register":
            return
        kind, msg = res
        if kind == "ok":
            self.make_login(prefill=name)
            self.notify("Conta criada! Entre com seus dados.", "ok")
        else:
            self._btn_text(self.reg_btn, "Criar conta")
            self.notify(msg, "error")
            self.shake()

    def key_missing(self):
        p = self.cfg.get("provider", "openai")
        return PROVIDERS[p]["needs_key"] and not api_key(p)

    def do_login(self):
        if getattr(self, "_login_busy", False):
            return
        name, pwd = self.u.get().strip(), self.p.get()
        if not name or not pwd:
            self.notify("Informe usuário e senha.", "error")
            self.shake()
            return
        self._login_busy = True
        self._btn_text(self.login_btn, "Entrando…")

        def work():
            try:
                self.lic.login(name, pwd)
                res = ("ok", "")
            except LicenseError as e:
                res = ("error", str(e))
            except Exception:
                res = ("error", "Não foi possível entrar. Tente de novo.")
            self.after(0, lambda: self._login_done(res, name))
        threading.Thread(target=work, daemon=True).start()

    def _login_done(self, res, name):
        self._login_busy = False
        if self.screen != "login":
            return
        kind, msg = res
        if kind != "ok":
            self._btn_text(self.login_btn, "Entrar")
            self.notify(msg, "error")
            self.shake()
            return
        self.user = name.strip()
        if self.remember.get():
            self.cfg["remember_user"] = self.user      # só o nome de usuário, nunca a senha
        else:
            self.cfg["remember_user"] = ""
        try:
            save_config(self.cfg)
        except OSError:
            pass
        self.view = {"status": "Pronto", "mod": "Módulo: —", "ex": "Exercício: —", "ans": "—"}
        self._start_license_watch()
        if self.key_missing():
            self.make_settings()
            self.notify("Configure sua API Key para começar.", "warn")
        else:
            self.make_dashboard()

    # ----- a licença é conferida de tempos em tempos: banir/expirar no painel vale na hora -----
    def _start_license_watch(self):
        self._stop_license_watch()
        self._license_job = self.after(LICENSE_CHECK_MS, self._license_tick)

    def _stop_license_watch(self):
        if self._license_job:
            try:
                self.after_cancel(self._license_job)
            except tk.TclError:
                pass
        self._license_job = None

    def _license_tick(self):
        self._license_job = None
        if not self.user:
            return

        def work():
            try:
                ok = self.lic.check()
            except Exception:
                ok = True        # sem internet não derruba; só uma resposta de bloqueio do servidor derruba
            self.after(0, lambda: self._license_result(ok))
        threading.Thread(target=work, daemon=True).start()

    def _license_result(self, ok):
        if not self.user:
            return
        if ok:
            self._license_job = self.after(LICENSE_CHECK_MS, self._license_tick)
            return
        self.user = None
        self.make_login()
        self.notify("Sua licença foi encerrada ou a conta foi desativada. Entre novamente.", "warn")

    def logout(self):
        self._stop_license_watch()
        self.user = None
        self.make_login()

    def make_dashboard(self):
        self.clear()
        self.fit(self.DASH_SIZE)
        self.screen = "dashboard"

        col = self.new_col(420)
        # Os controles agora fazem parte da própria coluna: ficam logo acima do wordmark,
        # sem uma faixa independente sobreposta que podia recortar o Canvas dos botões.
        top = tk.Frame(col, bg=BG, height=44)
        top.pack(fill="x", pady=(0, 2))
        top.pack_propagate(False)
        RoundButton(top, "Sair", self.logout, style="secondary", height=38, width=76,
                    font=(FONT_SEMI, 10)).pack(side="left", anchor="n")
        RoundButton(top, "Configurações", self.make_settings, style="secondary", height=38,
                    width=130, font=(FONT_SEMI, 10)).pack(side="right", anchor="n")

        self.wordmark(col, 22)
        tk.Label(col, text="Pronto para analisar sua próxima questão", bg=BG, fg=MUTED,
                 font=(FONT, 11)).pack(pady=(22, 8))
        shortcut = tk.Frame(col, bg=BG)
        shortcut.pack(pady=(0, 16))
        tk.Label(shortcut, text="F8", bg=FIELD, fg=TEXT, font=(FONT_SEMI, 9),
                 padx=8, pady=3, relief="flat", bd=0).pack(side="left")
        tk.Label(shortcut, text="  captura a tela e envia para análise", bg=BG, fg=MUTED,
                 font=(FONT, 9)).pack(side="left")
        RoundButton(col, "CAPTURAR QUESTÃO", self.request_capture, height=46, width=280).pack()

        # status com bolinha colorida
        srow = tk.Frame(col, bg=BG)
        srow.pack(pady=(18, 14))
        self.dot = tk.Label(srow, bg=BG, bd=0)
        self.dot.pack(side="left", padx=(0, 8))
        self.status = tk.Label(srow, text="", bg=BG, fg=MUTED, font=(FONT, 10))
        self.status.pack(side="left")

        # card do resultado
        card = Card(col, height=224)
        card.pack(fill="x")
        inner = card.inner
        result_head = tk.Frame(inner, bg=PANEL)
        result_head.pack(fill="x", pady=(0, 8))
        tk.Frame(result_head, bg=ACCENT, width=3, height=13).pack(side="left", padx=(0, 8))
        tk.Label(result_head, text="RESULTADO DA ANÁLISE", bg=PANEL, fg="#b7b3d6",
                 font=(FONT_SEMI, 8), anchor="w").pack(side="left")
        info = tk.Frame(inner, bg=PANEL)
        info.pack(fill="x")
        info.columnconfigure((0, 1), weight=1, uniform="info")
        self.mod = self._info_cell(info, 0, "MÓDULO")
        self.ex = self._info_cell(info, 1, "EXERCÍCIO")
        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", pady=(12, 0))
        box = tk.Frame(inner, bg=PANEL, height=110)
        box.pack(fill="x")
        box.pack_propagate(False)
        self.ans = tk.Label(box, text="", bg=PANEL, fg=ACCENT, font=(FONT, 64, "bold"))
        self.ans.place(relx=0.5, rely=0.44, anchor="center")
        self.copy_hint = tk.Label(box, text="Clique para copiar", bg=PANEL, fg=MUTED,
                                  font=(FONT, 8), cursor="hand2")
        for w in (self.ans, self.copy_hint):
            w.bind("<Button-1>", lambda e: self.copy_answer())
        self.paint()

    def _info_cell(self, parent, column, title):
        cell = tk.Frame(parent, bg=PANEL)
        cell.grid(row=0, column=column, sticky="n")
        tk.Label(cell, text=title, bg=PANEL, fg=MUTED, font=(FONT, 8)).pack()
        val = tk.Label(cell, text="—", bg=PANEL, fg=TEXT, font=(FONT, 11),
                       wraplength=170, justify="center")
        val.pack(pady=(3, 0))
        return val

    @staticmethod
    def _val(text):
        """'Módulo: Matemática' -> 'Matemática' (o título já aparece acima, no card)."""
        return text.split(": ", 1)[1] if ": " in text else text

    def _set_dot(self, color):
        img = self._dot_cache.get(color)
        if img is None:
            img = self._dot_cache[color] = ImageTk.PhotoImage(render_dot(color, 10, BG))
        self.dot.config(image=img)

    def paint(self):
        if self.screen != "dashboard":
            return
        try:
            self.status.config(text=self.view["status"])
            self.mod.config(text=self._val(self.view["mod"]))
            self.ex.config(text=self._val(self.view["ex"]))
            ans = self.view["ans"]
            if ans == "—":      # sem resposta ainda: só uma dica discreta
                self.ans.config(text="A resposta aparece aqui", font=(FONT, 10), fg=MUTED,
                                cursor="")
            else:
                self.ans.config(text=ans, font=(FONT, 64, "bold"), fg=ACCENT)
            ready = ans not in ("—", "…", "!", "")
            self.ans.config(cursor="hand2" if ready else "")
            if ready:
                self.copy_hint.config(text="Clique para copiar", fg=MUTED)
                self.copy_hint.place(relx=0.5, rely=1.0, anchor="s", y=-2)
            else:
                self.copy_hint.place_forget()
            # bolinha: roxa (pulsando, ver _load_tick) ocupado, vermelha erro, verde pronto
            if self.busy:
                self._set_dot(ACCENT)
            elif self.view["status"].startswith("Erro"):
                self._set_dot("#ff8d99")
            else:
                self._set_dot("#6ee7a0")
        except tk.TclError:
            pass

    def copy_answer(self):
        ans = self.view.get("ans", "")
        if ans in ("—", "…", "!", ""):
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(ans)
            self.update_idletasks()
            self.copy_hint.config(text="Copiado ✓", fg="#6ee7a0")
            Tween(self.ans).run(320, lambda t: self.ans.config(fg=lerp_color("#ffffff", ACCENT, t)))
            if self._copy_job:
                self.after_cancel(self._copy_job)
            self._copy_job = self.after(1600, self._reset_copy_hint)
        except tk.TclError:
            pass

    def _reset_copy_hint(self):
        self._copy_job = None
        try:
            if self.screen == "dashboard" and self.view["ans"] not in ("—", "…", "!", ""):
                self.copy_hint.config(text="Clique para copiar", fg=MUTED)
        except tk.TclError:
            pass

    def make_settings(self):
        self.clear()
        compact = self.winfo_screenheight() < 900
        self._compact_settings = compact
        settings_top = 16 if compact else self.SETTINGS_TOP
        self.fit((self.SETTINGS_SIZE[0], self.SETTINGS_SIZE[1] - (34 if compact else 0)))
        self.screen = "settings"
        col = self.new_col(420, top=settings_top, scroll=compact)

        self.heading(col, "Configurações", (FONT_LIGHT, 21 if compact else 24))

        def vpad(pair):
            """Comprime apenas espaços verticais; os controles mantêm o mesmo tamanho."""
            if not compact:
                return pair
            return tuple(max(2, round(value * 0.62)) for value in pair)

        models = dict(self.cfg.get("models") or {})
        state = {"current": self.cfg.get("provider", "openai")}

        self.section(col, "Provedor e modelo", pady=vpad((14, 5)))
        self.lbl(col, "Provedor de IA", pady=vpad((0, 5)))
        provider_icons = {
            "OpenAI (ChatGPT)": ("O", "#5b5b62"),
            "Google Gemini": ("G", "#4285f4"),
            "Google Gemini (Grátis)": ("G", "#34a853"),
            "Anthropic Claude": ("A", "#c87552"),
            "Universal (API compatível com OpenAI)": ("API", ACCENT),
        }
        provider_icons.update({
            PROVIDERS["openai"]["label"]: self.provider_icon_imgs.get("openai",
                provider_icons[PROVIDERS["openai"]["label"]]),
            PROVIDERS["gemini"]["label"]: self.provider_icon_imgs.get("gemini",
                provider_icons[PROVIDERS["gemini"]["label"]]),
            PROVIDERS["gemini_free"]["label"]: self.provider_icon_imgs.get("gemini",
                provider_icons[PROVIDERS["gemini_free"]["label"]]),
            PROVIDERS["claude"]["label"]: self.provider_icon_imgs.get("claude",
                provider_icons[PROVIDERS["claude"]["label"]]),
            PROVIDERS["universal"]["label"]: self.provider_icon_imgs.get("universal",
                provider_icons[PROVIDERS["universal"]["label"]]),
        })
        prov = Select(col, self, values=[m["label"] for m in PROVIDERS.values()],
                      value=PROVIDERS[state["current"]]["label"],
                      on_select=lambda v: refresh(), option_icons=provider_icons)
        prov.pack(fill="x")

        url_lbl = tk.Label(col, text="URL base (API compatível com OpenAI)", bg=BG, fg=MUTED,
                           font=(FONT, 10), anchor="w")
        url_f = Field(col, lambda c: self.entry(c))
        url = url_f.inner
        url.insert(0, self.cfg.get("base_url", DEFAULT_UNIVERSAL_URL))

        key_lbl = self.lbl(col, "API Key", pady=vpad((12, 5)))
        key_f = Field(col, lambda c: self.entry(c, show="•")); key_f.pack(fill="x")
        e = key_f.inner
        key_f.attach_right(EyeToggle(key_f, e), 26)
        # Mantém uma linha reservada mesmo enquanto o keyring é consultado em segundo
        # plano. Sem essa reserva, o texto "Chave já salva..." alterava a altura pedida
        # do formulário durante o resize e o Windows corrigia a janela em um salto.
        hint = tk.Label(col, text="", bg=BG, fg=MUTED, font=(FONT, 9), anchor="w", height=1)
        hint.pack(fill="x", pady=(4, 0))
        # só aparecem no provedor grátis: atalho para criar a chave e aviso de privacidade
        free_link = tk.Label(col, text="Criar chave grátis no Google AI Studio  ↗", bg=BG,
                             fg=ACCENT, font=(FONT, 9), anchor="w", cursor="hand2")
        free_link.bind("<Button-1>", lambda ev: webbrowser.open(PROVIDERS["gemini_free"]["key_url"]))
        free_link.bind("<Enter>", lambda ev: free_link.config(font=(FONT, 9, "underline")))
        free_link.bind("<Leave>", lambda ev: free_link.config(font=(FONT, 9)))
        free_note = tk.Label(col, text="No plano grátis, o Google pode usar o que for enviado "
                             "(inclusive a captura de tela) para melhorar os produtos dele.",
                             bg=BG, fg=MUTED, font=(FONT, 9), anchor="w", justify="left",
                             wraplength=410)

        self.section(col, "Captura e conexão", pady=vpad((12, 5)))
        self.lbl(col, "Modelo (pode digitar outro)", pady=vpad((0, 5)))
        m = Select(col, self, values=[], value="", editable=True)
        m.pack(fill="x")

        self.lbl(col, "Monitor de captura", pady=vpad((12, 5)))
        # O MSS reserva o índice 0 para a área virtual de todos os monitores;
        # os monitores físicos começam no índice 1. A interface mostra nomes
        # amigáveis, mas continua salvando exatamente os mesmos índices.
        try:
            with mss.mss() as _screen_probe:
                monitor_info = list(_screen_probe.monitors[1:])
        except Exception:
            monitor_info = []
        monitor_labels = ["Todos os monitores"]
        monitor_values = {monitor_labels[0]: 0}
        for index, info in enumerate(monitor_info, start=1):
            label = f"Monitor {index} — {info['width']}×{info['height']}"
            monitor_labels.append(label)
            monitor_values[label] = index
        saved_monitor = int(self.cfg.get("monitor", 0) or 0)
        monitor_value = next(
            (label for label, value in monitor_values.items() if value == saved_monitor),
            monitor_labels[0],
        )
        mon = Select(col, self, values=monitor_labels, value=monitor_value)
        mon.pack(fill="x")

        # --- chaves salvas: o keyring (Credential Manager) é lento e travava a troca de
        # provedor quando consultado na hora. Agora é lido UMA vez, em segundo plano. ---
        saved = {}

        def load_saved():
            for pid in list(PROVIDERS):
                saved[pid] = bool(api_key(pid))
        threading.Thread(target=load_saved, daemon=True).start()

        def hint_for(p):
            if saved.get(p):
                return "Chave já salva. Deixe vazio para manter."
            if not PROVIDERS[p]["needs_key"]:
                return "Opcional para servidores locais (Ollama, LM Studio)."
            return ""

        def poll_saved():
            if self.screen != "settings":
                return
            if len(saved) < len(PROVIDERS):
                self.after(60, poll_saved)
            else:
                hint.config(text=hint_for(state["current"]))
        self.after(60, poll_saved)

        # --- tamanho dos blocos que variam por provedor (a janela NÃO muda ao trocar:
        # ela já nasce com espaço para o maior deles, então nada é redimensionado) ---
        url_extra = url_lbl.winfo_reqheight() + 17 + url_f.winfo_reqheight()
        free_extra = free_link.winfo_reqheight() + free_note.winfo_reqheight() + 6
        max_extra = max(url_extra, free_extra)

        def extra_for(p):
            if p == "universal":
                return url_extra
            return free_extra if PROVIDERS[p].get("free") else 0

        fades = {}

        def fade_in(lbl, color):
            lbl.config(fg=BG)
            tw = fades.setdefault(lbl, Tween(lbl))
            tw.run(240, lambda t: lbl.config(fg=lerp_color(BG, color, t)))

        def refresh(*_):
            prev = state["current"]
            if m.get().strip():
                models[prev] = m.get().strip()
            p = provider_from_label(prov.get())
            state["current"] = p
            meta = PROVIDERS[p]
            m.set_values(meta["models"])
            m.set(models.get(p) or (meta["models"][0] if meta["models"] else ""))
            e.delete(0, "end")
            key_lbl.config(text=f"API Key — {meta['label']}")
            hint.config(text=hint_for(p))
            if meta.get("free"):
                if not free_link.winfo_manager():
                    free_link.pack(fill="x", pady=vpad((3, 0)), after=hint)
                    free_note.pack(fill="x", pady=vpad((3, 0)), after=free_link)
                    fade_in(free_link, ACCENT)
                    fade_in(free_note, MUTED)
            else:
                free_link.pack_forget()
                free_note.pack_forget()
            if p == "universal":
                if not url_lbl.winfo_manager():
                    url_lbl.pack(fill="x", pady=vpad((12, 5)), before=key_lbl)
                    url_f.pack(fill="x", before=key_lbl)
                    fade_in(url_lbl, MUTED)
            else:
                url_lbl.pack_forget()
                url_f.pack_forget()
            # quanto ainda pode aparecer (a janela já tem esse espaço reservado)
            self._fit_reserve = max_extra - extra_for(p)

        refresh()

        def save():
            try:
                p = provider_from_label(prov.get())
                model = m.get().strip()
                if not model:
                    raise ValueError("Informe o modelo.")
                if p == "universal" and not url.get().strip().lower().startswith("http"):
                    raise ValueError("Informe a URL base (começa com http).")
                monitor = monitor_values.get(mon.get(), 0)
                if e.get().strip():
                    set_api_key(p, e.get().strip())
                models[p] = model
                self.cfg = {
                    **self.cfg,
                    "provider": p,
                    "models": models,
                    "base_url": url.get().strip() or DEFAULT_UNIVERSAL_URL,
                    "monitor": monitor,
                }
                save_config(self.cfg)
            except Exception as x:
                self.notify(str(x), "error")
                self.shake()
                return
            self.make_dashboard()
            self.notify("Configurações salvas.", "ok")

        test_state = {"busy": False}

        def do_test():
            if test_state["busy"]:
                return
            p = provider_from_label(prov.get())
            model = m.get().strip()
            key = e.get().strip() or api_key(p)
            try:
                if PROVIDERS[p]["needs_key"] and not key:
                    raise ValueError("Informe a API Key para testar.")
                if not model:
                    raise ValueError("Informe o modelo.")
                if p == "universal" and not url.get().strip().lower().startswith("http"):
                    raise ValueError("Informe a URL base (começa com http).")
            except ValueError as x:
                self.notify(str(x), "error")
                self.shake()
                return
            base = url.get().strip() or DEFAULT_UNIVERSAL_URL
            test_state["busy"] = True
            test_btn.text = "Testando…"
            test_btn.draw()

            def work():
                try:
                    test_connection(p, model, key, base)
                    res = ("ok", "Conexão funcionando. Chave e modelo estão certos.")
                except (RateLimit, RateLimitError):
                    res = ("warn", "A chave é válida, mas o provedor limitou as requisições "
                                   "agora. Tente de novo em instantes.")
                except Exception as x:
                    res = ("error", str(x)[:240] or "Não foi possível conectar.")
                self.after(0, lambda: finish(*res))

            def finish(kind, msg):
                test_state["busy"] = False
                try:
                    test_btn.text = "Testar conexão"
                    test_btn.draw()
                except tk.TclError:
                    return
                if self.screen == "settings":
                    self.notify(msg, kind)

            threading.Thread(target=work, daemon=True).start()

        btns = tk.Frame(col, bg=BG)
        btns.pack(fill="x", pady=vpad((20, 10)))
        btns.columnconfigure((0, 1), weight=1, uniform="btn")
        test_btn = RoundButton(btns, "Testar conexão", do_test, style="secondary")
        test_btn.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        RoundButton(btns, "Salvar", save).grid(row=0, column=1, sticky="ew", padx=(5, 0))
        RoundButton(col, "Voltar", self.make_dashboard, style="secondary").pack(fill="x")

    # ----- animação de carregamento (pontinhos + letra pulsando) -----
    def start_loading(self):
        if self.loading:
            return
        self.loading = True
        self._load_tick()

    def stop_loading(self):
        self.loading = False

    def _load_tick(self):
        if not self.loading:
            return
        if self.screen == "dashboard":
            try:
                ph = time.perf_counter()
                dots = ("." * (int(ph * 3) % 4)).ljust(3)
                self.status.config(text=self.view["status"] + dots)
                k = (math.sin(ph * 5) + 1) / 2
                self.ans.config(fg=lerp_color(BORDER, ACCENT, k))
                self._set_dot(lerp_color("#3b3566", ACCENT, round(k * 12) / 12))
            except tk.TclError:
                pass
        self.after(16, self._load_tick)

    def reveal(self, color):
        """A letra da resposta aparece em fade."""
        if self.screen != "dashboard":
            return
        Tween(self.ans).run(420, lambda t: self.ans.config(fg=lerp_color(PANEL, color, t)))

    # ----- captura -----
    def hotkey(self, key):
        if key == keyboard.Key.f8:
            self.after(0, self.request_capture)

    def request_capture(self):
        if self.busy or self.screen != "dashboard":
            return
        self.busy = True
        self.view = {"status": "Capturando tela", "mod": "Módulo: —",
                     "ex": "Exercício: —", "ans": "…"}
        self.paint()
        self.start_loading()
        try:
            self.iconify()
        except Exception:
            pass
        threading.Thread(target=self.worker, daemon=True).start()

    def worker(self):
        try:
            time.sleep(.35)
            p = capture(int(self.cfg.get("monitor", 0)))
            self.after(0, self.show_processing)
            result = solve(p, self.cfg)
            self.after(0, lambda: self.done(result))
        except Exception as e:
            msg = str(e)
            self.after(0, lambda msg=msg: self.fail(msg))

    def show_processing(self):
        self.deiconify()
        try:
            self.lift()
        except Exception:
            pass
        self.view["status"] = "Analisando questão"
        self.paint()

    def done(self, r):
        self.deiconify(); self.lift()
        used_model = r.get("_model", "")
        self.view = {
            "status": "Resposta encontrada" + (f" • {used_model}" if used_model else ""),
            "mod": "Módulo: " + str(r.get("module") or "não identificado"),
            "ex": "Exercício: " + str(r.get("exercise") or "não identificado"),
            "ans": r.get("answer", "?"),
        }
        self.busy = False
        self.stop_loading()
        self.paint()
        self.reveal(ACCENT)

    def fail(self, msg):
        self.deiconify(); self.lift()
        self.view = {"status": "Erro", "mod": "Módulo: —", "ex": "Exercício: —", "ans": "!"}
        self.busy = False
        self.stop_loading()
        self.paint()
        self.reveal("#ff8d99")
        if "rate limit" in msg.lower() or "limite temporário" in msg.lower() or "429" in msg:
            self.notify(
                "O provedor de IA limitou temporariamente novas requisições. O Universo Bot "
                "tentou outros modelos automaticamente. Aguarde o limite resetar e tente de novo.",
                "warn")
        else:
            self.notify(msg, "error")

def boost_timer():
    """O timer padrão do Windows tem ~15,6 ms de resolução, o que faz after(10) oscilar
    entre 15 e 31 ms (animação 'dando soquinhos'). Pede 1 ms enquanto o app está aberto."""
    if os.name != "nt":
        return
    try:
        import ctypes, atexit
        ctypes.windll.winmm.timeBeginPeriod(1)
        atexit.register(lambda: ctypes.windll.winmm.timeEndPeriod(1))
    except Exception:
        pass

if __name__ == "__main__":
    set_windows_app_user_model_id()
    boost_timer()
    App().mainloop()
