import re
import time
import hashlib
import requests
import json
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters

TELEGRAM_TOKEN = "8581469156:AAGFQnyMK35JMkhvUKz8W3NxJ3lsGQEGn_8"
SHOPEE_APP_KEY = "18310850939"
SHOPEE_APP_SECRET = "N2LZ2EFF4T6LTO4MTTZKUXPR5JSFB7XL"

# =============================
# MELHORAR IMAGEM ML
# =============================

def melhorar_imagem(url):

    if not url:
        return url

    url = url.replace("NQ_NP_2X","NQ_NP_4X")
    url = url.replace("NQ_NP_3X","NQ_NP_4X")
    url = url.replace("NQ_NP_60","NQ_NP_1200")

    return url


# =============================
# EXTRAIR ID
# =============================

def extrair_id(link, html_content=None):

    # padrão MLB clássico
    ml = re.search(r"MLB[-_]?(\d+)", link, re.IGNORECASE)
    if ml:
        return ("ML", ml.group(1))

    # padrão /p/MLB123
    ml2 = re.search(r"/p/MLB(\d+)", link, re.IGNORECASE)
    if ml2:
        return ("ML", ml2.group(1))

    # Shopee
    sh = re.search(r"i\.(\d+)\.(\d+)", link)
    if sh:
        return ("SH", f"{sh.group(1)}/{sh.group(2)}")

    # tentar pegar do HTML
    if html_content:

        soup = BeautifulSoup(html_content,"html.parser")

        # procurar qualquer link MLB
        for a in soup.find_all("a",href=True):

            href = a["href"]

            ml3 = re.search(r"MLB[-_]?(\d+)", href, re.IGNORECASE)

            if ml3:
                return ("ML", ml3.group(1))

    return (None,None)


# =============================
# MERCADO LIVRE
# =============================

# =============================
# MERCADO LIVRE (VERSÃO ROBUSTA)
# =============================

def buscar_produto_ml(item_id):

    url = f"https://www.mercadolivre.com.br/p/MLB{item_id}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "pt-BR,pt;q=0.9"
    }

    res = requests.get(url, headers=headers, timeout=15)
    
    # Se não encontrar na página de catálogo (/p/), tenta a página de produto direto
    if res.status_code != 200:
        url = f"https://produto.mercadolivre.com.br/MLB-{item_id}"
        res = requests.get(url, headers=headers, timeout=15)

    soup = BeautifulSoup(res.text, "html.parser")

    # Nome do produto
    nome_tag = soup.find("h1", {"class": "ui-pdp-title"})
    nome = nome_tag.text.strip() if nome_tag else "Produto"

    # --- LÓGICA DE PREÇO CORRIGIDA ---
    # Buscamos a meta tag específica que contém o valor numérico puro
    meta_preco = soup.find("meta", {"property": "product:price:amount"})
    
    if meta_preco:
        preco = float(meta_preco["content"])
    else:
        # Fallback: tenta encontrar o preço no esquema de dados JSON da página
        try:
            json_data = soup.find("script", {"type": "application/ld+json"})
            if json_data:
                dados = json.loads(json_data.text)
                # O JSON pode ser uma lista ou um objeto único
                if isinstance(dados, list):
                    preco = float(dados[0]['offers']['price'])
                else:
                    preco = float(dados['offers']['price'])
            else:
                preco = 0.0
        except:
            preco = 0.0

    # Imagem
    meta_img = soup.find("meta", property="og:image")
    foto = meta_img["content"] if meta_img else ""
    foto = melhorar_imagem(foto)

    return {
        "nome": nome,
        "preco": preco,
        "foto": foto
    }


# =============================
# SHOPEE
# =============================

def buscar_produto_shopee(link_expandido):

    match = re.search(r"i\.(\d+)\.(\d+)",link_expandido)

    if not match:
        return None

    shop_id,item_id = int(match.group(1)),int(match.group(2))

    url_api = "https://open-api.affiliate.shopee.com.br/graphql"

    timestamp = int(time.time())

    query = f'''
    query {{
      productOfferV2(itemId:{item_id},shopId:{shop_id}) {{
        nodes {{
          productName
          priceMin
          imageUrl
          offerLink
        }}
      }}
    }}
    '''

    body = json.dumps({"query":query})

    payload = f"{SHOPEE_APP_KEY}{timestamp}{body}{SHOPEE_APP_SECRET}"

    signature = hashlib.sha256(payload.encode()).hexdigest()

    headers = {
        "Authorization":f"SHA256 Credential={SHOPEE_APP_KEY}, Signature={signature}, Timestamp={timestamp}",
        "Content-Type":"application/json"
    }

    r = requests.post(url_api,data=body,headers=headers)

    dados = r.json()

    prod = dados["data"]["productOfferV2"]["nodes"][0]

    return {
        "nome":prod["productName"],
        "preco":prod["priceMin"],
        "foto":prod["imageUrl"],
        "link_afiliado":prod.get("offerLink")
    }


# =============================
# BOT
# =============================

async def responder(update:Update,context:ContextTypes.DEFAULT_TYPE):

    link = update.message.text

    await update.message.reply_text("🔎 Rastreando produto...")

    try:

        res = requests.get(link,allow_redirects=True,headers={"User-Agent":"Mozilla/5.0"})

        plat,item_id = extrair_id(res.url,res.text)

        if plat == "ML":

            produto = buscar_produto_ml(item_id)

        elif plat == "SH":

            produto = buscar_produto_shopee(res.url)

        else:

            await update.message.reply_text("❌ Não consegui identificar o produto")
            return

        msg = f"""
🛍 {produto['nome']}

💰 R$ {produto['preco']}

🛒 {link}
"""

        await update.message.reply_photo(produto["foto"],caption=msg)

    except:

        await update.message.reply_text("Erro ao processar link")


# =============================
# START
# =============================

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), responder))

print("Bot rodando...")

app.run_polling()