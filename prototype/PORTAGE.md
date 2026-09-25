# Portage minimal du prototype

Le prototype a été livré pour `mistralai==0.4.2` et `langchain==0.3.23`. Ces API n'existent
plus dans l'environnement du projet (`mistralai` 2.10.1, `langchain` 1.x), le code ne
s'exécutait donc pas.

Objectif du portage : **rendre le prototype exécutable sans modifier son comportement**, afin
de mesurer une baseline fidèle. Aucune modification de logique, de prompt, de paramètres
(chunking, `k`, modèle, température) ni de gestion d'erreurs. Chaque ligne modifiée est
marquée `# [PORTAGE]` dans le code.

## Changements d'API

| Fichier | Avant (prototype) | Après |
|---|---|---|
| `utils/vector_store.py`, `MistralChat.py` | `from mistralai.client import MistralClient` | `from mistralai.client import Mistral` |
| `utils/vector_store.py`, `MistralChat.py` | `MistralClient(api_key=...)` | `Mistral(api_key=...)` |
| `utils/vector_store.py` (×2) | `client.embeddings(model=..., input=[...])` | `client.embeddings.create(model=..., inputs=[...])` |
| `utils/vector_store.py` (×2) | `except MistralAPIException` | `except MistralError` (classe de base des erreurs HTTP, mêmes attributs `status_code` / `message`) |
| `utils/vector_store.py` | `from langchain.text_splitter import ...` | `from langchain_text_splitters import ...` |
| `MistralChat.py` | `client.chat(...)` | `client.chat.complete(...)` |
| `MistralChat.py` | `ChatMessage(role=..., content=...)` | `{"role": ..., "content": ...}` |
| `utils/data_loader.py` | `from PyPDF2 import PdfReader` | `from pypdf import PdfReader` (successeur maintenu, même API) |

## Changements de chemins

Les fichiers ont été rangés dans l'arborescence du projet. Les chemins de `utils/config.py`
sont désormais ancrés à la racine du projet (`PROJECT_ROOT`) au lieu du répertoire courant.

| Constante | Avant | Après |
|---|---|---|
| `INPUT_DIR` | `inputs` | `data/raw` |
| `VECTOR_DB_DIR` | `vector_db` | `data/vector_store/prototype` |
| `DATABASE_DIR` | `database` | `data/database` |

L'index FAISS et les chunks d'origine (302 chunks, `mistral-embed`, dimension 1024) sont
réutilisés tels quels depuis `data/vector_store/prototype/` : la baseline est mesurée sur
l'index livré, sans ré-indexation.

## Défauts connus volontairement conservés

Relevés lors de l'audit, laissés en l'état pour ne pas biaiser la baseline :

- échec d'un lot d'embeddings → insertion silencieuse de vecteurs nuls ; second `except Exception` inatteignable ;
- import OCR en `try/except` qui désactive l'OCR sans erreur bloquante ;
- prompt orienté « fans / animer le débat », sans consigne de fidélité au contexte ;
- feuilles Excel indexées via `df.to_string()` (en-têtes perdus après le premier chunk), feuille « Analyse Vide » indexée.
