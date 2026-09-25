"""Nettoyage du texte OCR des threads Reddit et découpage en messages puis en documents.

Le markdown produit par Mistral OCR contient, en plus des messages, tout le décor de la
page web capturée : en-tête et pied de chaque page (date, titre, URL, pagination), menus
(« Se connecter »...), contrôles de vote (« Répondre », flèches, compteurs) et publicités
sponsorisées. On retire ce décor, on recolle les pages (un commentaire peut être coupé par
un saut de page), puis on découpe le thread en messages : le post initial et chaque
commentaire, avec son auteur.

Les documents indexés regroupent des commentaires consécutifs (un seul commentaire est
souvent trop court pour être retrouvé seul) et sont tous préfixés par le titre du thread,
pour que chaque extrait récupéré garde son contexte.
"""

import re
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

from sportsee_llm_eval.preparation.ocr import load_or_ocr, reddit_pdfs
from sportsee_llm_eval.preparation.schemas import IndexedDocument, RedditComment

# « auteur • -3 j », « auteur AO • -1 m. », « auteur • il y a 2 m. • Modifié il y a... »
# (« [supprimé] » : compte supprimé)
AUTHOR_LINE = re.compile(
    r"^(?P<author>\[supprimé\]|[\w-]+)(?: [\w-]+)? • (?:-|il y a )\s*\d+\s*(?:m|j|h|a)\b"
)
SPONSORED_LINE = re.compile(r"•.*Sponsorisé")
# « r/nba • il y a 1 m. » : méta du post initial ; toute occurrence suivante (r/nba, r/NBATalk...)
# ouvre la section « publications connexes » de Reddit, qui marque la fin du thread
SUBREDDIT_LINE = re.compile(r"^r/\w+ • il y a")
PAGE_DATE = re.compile(r"^\d{2}/\d{2}/\d{4} \d{2}[:.]\d{2}$")
PAGE_NUMBER = re.compile(r"^\d+/\d+$")
MORE_REPLIES = re.compile(r"^\d+ réponses? supplémentaires?$")
# Compteurs de votes et boutons, seuls sur leur ligne ou collés en fin de message :
# « 186 », « 7 7  Répondre ... », « 3 → □ Répondre ... », « ♀ 9 ♦ ☐ Répondre ... », « -2 ↓ »,
# « 1  \( \downarrow \)  □ Répondre ... » (flèche rendue en LaTeX par l'OCR)
VOTE_SYMBOLS = "○◯♀♦→←↑↓□☐"
_VOTE_TOKEN = rf"(?:\s|[{VOTE_SYMBOLS}]|\\\(|\\\)|\\(?:down|up)arrow)"
VOTE_SUFFIX = re.compile(
    rf"{_VOTE_TOKEN}*(?:-?\d+{_VOTE_TOKEN}*)*(?:Répondre)?[\s.…]*$"
)
VOTE_CONTROLS = re.compile(
    rf"^{_VOTE_TOKEN}*(?:-?\d+{_VOTE_TOKEN}*)*(?:Répondre)?[\s.…]*$"
)
UI_LINES = {
    "Accéder au contenu principal",
    "Rechercher dans r/nba",
    "Se connecter",
    "Partager",
    "Rejoindre la conversation",
    "Trier par : Meilleurs",
    "Rechercher des commentaires",
    "Comm. du top 1%",
    "En savoir plus",
    "Afficher plus de commentaires",
}
MIN_COMMENT_CHARS = 15
MAX_DOC_CHARS = 1500
OVERLAP_CHARS = 150


def _strip_markdown_heading(line: str) -> str:
    return line.lstrip("#").strip()


def _strip_vote_suffix(line: str) -> str:
    """Retire un compteur de votes collé en fin de ligne. Ne touche pas une phrase qui se
    termine par un nombre (« his rTS was 115. ») : il faut « Répondre » ou un symbole de vote.
    """
    match = VOTE_SUFFIX.search(line)
    if match and ("Répondre" in match[0] or any(c in match[0] for c in VOTE_SYMBOLS)):
        return line[: match.start()].rstrip()
    return line


def _is_noise(line: str, titles: set[str]) -> bool:
    bare = _strip_markdown_heading(line)
    return (
        not bare
        or bare in UI_LINES
        or "Comm. du top 1%" in bare
        or bare in titles
        or bare.endswith(": r/nba")
        or bare.startswith(("https://www.reddit.com/", "!["))
        or PAGE_DATE.match(bare) is not None
        or PAGE_NUMBER.match(bare) is not None
        or MORE_REPLIES.match(bare) is not None
        or VOTE_CONTROLS.match(bare) is not None
        or bare in {"a", "...", "↑", "↓", "☐"}
    )


def page_header_title(pages: list[str]) -> str:
    """Titre tel qu'affiché en en-tête de chaque page (2e ligne, après la date)."""
    lines = [line.strip() for line in pages[0].splitlines() if line.strip()]
    if len(lines) < 2 or not PAGE_DATE.match(lines[0]):
        raise ValueError("En-tête de page OCR inattendu (date puis titre)")
    return lines[1]


def thread_title(pages: list[str]) -> str:
    """Titre complet du thread. L'en-tête de page le tronque s'il est long (« ... ») :
    on récupère alors la version complète dans le corps du post."""
    header = page_header_title(pages).removesuffix(": r/nba").strip()
    if not header.endswith("..."):
        return header
    prefix = header.removesuffix("...").strip()
    for line in pages[0].splitlines():
        bare = _strip_markdown_heading(line.strip())
        if bare.startswith(prefix) and not bare.endswith("..."):
            return bare
    return header


def parse_thread(pages: list[str], thread_id: str) -> list[RedditComment]:
    """Découpe un thread OCR en messages (post initial + commentaires), décor retiré."""
    title = thread_title(pages)
    titles = {title, page_header_title(pages)}
    lines = [line.strip() for page in pages for line in page.splitlines()]

    messages: list[RedditComment] = []
    author: str | None = None
    buffer: list[str] = []
    mode = "header"  # header -> post -> comment | ad

    def flush() -> None:
        text = "\n".join(
            buffer
        ).strip()  # retours à la ligne conservés (tableaux markdown)
        if mode in {"post", "comment"} and len(text) >= MIN_COMMENT_CHARS:
            messages.append(
                RedditComment(
                    thread_id=thread_id,
                    thread_title=title,
                    author=author,
                    text=text,
                    is_post=mode == "post",
                )
            )
        buffer.clear()

    for line in lines:
        if SPONSORED_LINE.search(line):
            flush()
            mode = "ad"
            continue
        if SUBREDDIT_LINE.match(line):
            flush()
            if messages or mode != "header":
                break  # publications connexes : fin du thread
            mode, author = "post", None
            continue
        match = AUTHOR_LINE.match(
            _strip_markdown_heading(line)
        )  # parfois « #### auteur • ... »
        if match:
            flush()
            mode, author = "comment", match["author"]
            continue
        if mode == "post" and author is None and line and not line.startswith("#"):
            author = line.split()[
                0
            ]  # ligne qui suit « r/nba • il y a ... » : auteur du post
            continue
        if _strip_markdown_heading(line) == "Rejoindre la conversation":
            flush()
            mode = (
                "header"  # fin du post ou de la publicité, avant le premier commentaire
            )
            continue
        if mode in {"post", "comment"} and not _is_noise(line, titles):
            if not line.startswith(
                "|"
            ):  # lignes de tableau markdown conservées telles quelles
                line = _strip_vote_suffix(_strip_markdown_heading(line))
            if line:
                buffer.append(line)
    flush()
    return messages


def _format(message: RedditComment) -> str:
    who = message.author or "auteur inconnu"
    kind = "Post initial" if message.is_post else "Commentaire"
    return f"{kind} de {who} : {message.text}"


def thread_documents(
    messages: list[RedditComment], source: str
) -> list[IndexedDocument]:
    """Regroupe les messages consécutifs en documents d'au plus MAX_DOC_CHARS caractères."""
    if not messages:
        return []
    title = messages[0].thread_title
    prefix = f"Discussion Reddit r/nba « {title} »\n"
    documents: list[IndexedDocument] = []
    current: list[str] = []

    def emit(is_post: bool = False) -> None:
        if current:
            documents.append(
                IndexedDocument(
                    doc_id=f"reddit::{messages[0].thread_id}::{len(documents):03d}",
                    source_type="reddit",
                    source=source,
                    text=prefix + "\n".join(current),
                    thread_title=title,
                    is_thread_post=is_post,
                )
            )
            current.clear()

    # découpe aux frontières de paragraphe, de ligne puis de phrase, jamais au milieu d'un mot
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=MAX_DOC_CHARS - len(prefix),
        chunk_overlap=OVERLAP_CHARS,
        separators=["\n\n", "\n", ". ", " "],
    )
    for message in messages:
        piece = _format(message)
        # le post initial (souvent long, avec tableau) forme toujours son propre document
        if message.is_post or len(prefix) + len(piece) > MAX_DOC_CHARS:
            emit()
            for part in splitter.split_text(piece):
                current.append(part)
                emit(is_post=message.is_post)
            continue
        if len(prefix) + sum(len(p) + 1 for p in current) + len(piece) > MAX_DOC_CHARS:
            emit()
        current.append(piece)
    emit()
    return documents


def build_reddit_documents(raw_dir: Path | None = None) -> list[IndexedDocument]:
    documents = []
    for pdf in reddit_pdfs(raw_dir) if raw_dir else reddit_pdfs():
        thread_id = pdf.stem.lower().replace(" ", "_")
        messages = parse_thread(load_or_ocr(pdf), thread_id)
        documents += thread_documents(messages, source=pdf.name)
    return documents
