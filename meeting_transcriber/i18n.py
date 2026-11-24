"""Texts of the window and of the progress log in English, Italian, Spanish, French, Portuguese
and Chinese, plus the two saved choices: the interface language and the default meeting language.

On Linux the bundled Tk draws with X core fonts, which only cover Latin-1: Chinese is left out
of the interface languages there, and every other text must stay within Latin-1 (no "…", "—",
"’" or "œ").
"""

import json
import locale
import os
import sys

from .paths import DATA_DIR

SETTINGS = DATA_DIR / "settings.json"
DOTS = "…" if sys.platform == "win32" else "..."

# Interface languages, in the menu's order, with their own names.
UI_LANGUAGES = {"en": "English", "it": "Italiano", "es": "Español", "fr": "Français", "pt": "Português", "zh": "中文"}
if sys.platform != "win32":
    del UI_LANGUAGES["zh"]

# Meeting languages: what Whisper is told to expect ("auto" lets it detect the language).
MEETING_LANGUAGES = ("auto", "it", "en", "es", "fr", "pt", "zh")

T = {
    # --- window ---
    "add_videos": {
        "en": "Add recordings{dots}", "it": "Aggiungi registrazioni{dots}", "es": "Añadir grabaciones{dots}",
        "fr": "Ajouter des enregistrements{dots}", "pt": "Adicionar gravações{dots}", "zh": "添加录音{dots}"},
    "start_all": {
        "en": "Start all", "it": "Avvia tutti", "es": "Iniciar todos",
        "fr": "Tout lancer", "pt": "Iniciar todos", "zh": "全部开始"},
    "open_results": {
        "en": "Open results folder", "it": "Apri cartella risultati", "es": "Abrir carpeta de resultados",
        "fr": "Ouvrir le dossier des résultats", "pt": "Abrir pasta de resultados", "zh": "打开结果文件夹"},
    "guide": {"en": "Guide", "it": "Guida", "es": "Guía", "fr": "Guide", "pt": "Guia", "zh": "指南"},
    "glossary": {
        "en": "Glossary{dots}", "it": "Glossario{dots}", "es": "Glosario{dots}",
        "fr": "Glossaire{dots}", "pt": "Glossário{dots}", "zh": "术语表{dots}"},
    "ui_language": {
        "en": "Interface", "it": "Interfaccia", "es": "Interfaz",
        "fr": "Interface", "pt": "Interface", "zh": "界面语言"},
    "meeting_language": {
        "en": "Meeting language", "it": "Lingua della riunione", "es": "Idioma de la reunión",
        "fr": "Langue de la réunion", "pt": "Idioma da reunião", "zh": "会议语言"},
    "meeting_language_hint": {
        "en": "applies to every recording not started yet; a single row can then be changed with its own menu",
        "it": "vale per tutte le registrazioni non ancora avviate; poi si può cambiare una singola riga dal suo menu",
        "es": "se aplica a todas las grabaciones aún no iniciadas; luego cada fila se puede cambiar con su menú",
        "fr": "s'applique à tous les enregistrements pas encore lancés ; chaque ligne se modifie ensuite avec son menu",
        "pt": "vale para todas as gravações ainda não iniciadas; depois cada linha pode ser mudada no seu menu",
        "zh": "适用于所有尚未开始的录音；之后可用每一行自己的菜单单独修改"},
    "participants": {
        "en": "Participants", "it": "Partecipanti", "es": "Participantes",
        "fr": "Participants", "pt": "Participantes", "zh": "参会者"},
    "participants_hint": {
        "en": "optional, separated by commas (e.g. from the invitation): Whisper spells them right and voices "
              "called by first name get the full name. Applies to every recording not started yet",
        "it": "facoltativo, separati da virgole (per esempio dall'invito): Whisper li scrive giusti e le voci "
              "chiamate per nome ricevono nome e cognome. Vale per le registrazioni non ancora avviate",
        "es": "opcional, separados por comas (por ejemplo, de la invitación): Whisper los escribe bien y las voces "
              "llamadas por su nombre reciben nombre y apellido. Vale para las grabaciones aún no iniciadas",
        "fr": "facultatif, séparés par des virgules (par exemple depuis l'invitation) : Whisper les écrit bien et "
              "les voix appelées par leur prénom reçoivent prénom et nom. Vaut pour les enregistrements pas encore lancés",
        "pt": "opcional, separados por vírgulas (por exemplo, do convite): o Whisper escreve-os bem e as vozes "
              "chamadas pelo nome recebem nome e sobrenome. Vale para as gravações ainda não iniciadas",
        "zh": "可选，用逗号分隔（例如从会议邀请中复制）：Whisper 会正确拼写，按名字称呼的声音会得到全名。"
              "适用于所有尚未开始的录音"},
    "content_names": {
        "en": "Recognise speakers from what they say", "it": "Riconosci chi parla da quello che dice",
        "es": "Reconocer a los hablantes por lo que dicen", "fr": "Reconnaître les intervenants d'après ce qu'ils disent",
        "pt": "Reconhecer quem fala pelo que diz", "zh": "根据发言内容识别说话人"},
    "folder_name": {
        "en": "Results folder", "it": "Cartella dei risultati", "es": "Carpeta de resultados",
        "fr": "Dossier des résultats", "pt": "Pasta de resultados", "zh": "结果文件夹"},
    "folder_file": {
        "en": "name of the recording", "it": "nome della registrazione", "es": "nombre de la grabación",
        "fr": "nom de l'enregistrement", "pt": "nome da gravação", "zh": "录音文件名"},
    "folder_title": {
        "en": "date + title from the content", "it": "data + titolo dal contenuto", "es": "fecha + título del contenido",
        "fr": "date + titre tiré du contenu", "pt": "data + título do conteúdo", "zh": "日期 + 根据内容生成的标题"},
    "checking_hardware": {
        "en": "Checking the hardware{dots}", "it": "Verifica dell'hardware{dots}",
        "es": "Comprobando el hardware{dots}", "fr": "Vérification du matériel{dots}",
        "pt": "Verificando o hardware{dots}", "zh": "正在检查硬件{dots}"},
    "no_pyannote_banner": {
        "en": "pyannote model not available: speakers will be assigned from the video only (less accurate). See the guide.",
        "it": "Modello pyannote non disponibile: gli speaker verranno attribuiti solo dal video (meno preciso). Vedi la guida.",
        "es": "Modelo pyannote no disponible: los hablantes se asignarán solo a partir del vídeo (menos preciso). Consulta la guía.",
        "fr": "Modèle pyannote indisponible : les intervenants seront attribués uniquement à partir de la vidéo (moins précis). Voir le guide.",
        "pt": "Modelo pyannote indisponível: os oradores serão atribuídos apenas a partir do vídeo (menos preciso). Veja o guia.",
        "zh": "pyannote 模型不可用：将只根据视频判断说话人（准确度较低）。请参阅指南。"},
    "total": {"en": "Total", "it": "Totale", "es": "Total", "fr": "Total", "pt": "Total", "zh": "总计"},
    "empty_list": {
        "en": "No recordings in the list (videos or audio files): use \"{add}\".",
        "it": "Nessuna registrazione in coda (video o file audio): usa \"{add}\".",
        "es": "No hay grabaciones en la lista (vídeos o archivos de audio): usa \"{add}\".",
        "fr": "Aucun enregistrement dans la liste (vidéos ou fichiers audio) : utilisez \"{add}\".",
        "pt": "Nenhuma gravação na lista (vídeos ou arquivos de áudio): use \"{add}\".",
        "zh": "列表中没有录音（视频或音频文件）：请使用“{add}”。"},
    "pick_title": {
        "en": "Add one or more recordings", "it": "Aggiungi una o più registrazioni",
        "es": "Añade una o más grabaciones", "fr": "Ajouter un ou plusieurs enregistrements",
        "pt": "Adicione uma ou mais gravações", "zh": "添加一个或多个录音"},
    "recordings": {
        "en": "Recordings", "it": "Registrazioni", "es": "Grabaciones",
        "fr": "Enregistrements", "pt": "Gravações", "zh": "录音"},
    "all_files": {
        "en": "All files", "it": "Tutti i file", "es": "Todos los archivos",
        "fr": "Tous les fichiers", "pt": "Todos os arquivos", "zh": "所有文件"},
    "results_in": {
        "en": "Results in: {folders}", "it": "Risultati in: {folders}", "es": "Resultados en: {folders}",
        "fr": "Résultats dans : {folders}", "pt": "Resultados em: {folders}", "zh": "结果保存在：{folders}"},
    "cannot_read": {
        "en": "Cannot read {name}: {error}", "it": "Impossibile leggere {name}: {error}",
        "es": "No se puede leer {name}: {error}", "fr": "Impossible de lire {name} : {error}",
        "pt": "Não é possível ler {name}: {error}", "zh": "无法读取 {name}：{error}"},
    "error_line": {
        "en": "ERROR: {error}", "it": "ERRORE: {error}", "es": "ERROR: {error}",
        "fr": "ERREUR : {error}", "pt": "ERRO: {error}", "zh": "错误：{error}"},
    "not_completed": {
        "en": "{n} file(s) not completed: see the log.", "it": "{n} file non completati: vedi il log.",
        "es": "{n} archivo(s) sin completar: consulta el registro.",
        "fr": "{n} fichier(s) non terminé(s) : voir le journal.",
        "pt": "{n} arquivo(s) não concluído(s): veja o registro.", "zh": "{n} 个文件未完成：请查看日志。"},
    "file_not_found": {
        "en": "File not found:\n{path}", "it": "File non trovato:\n{path}", "es": "Archivo no encontrado:\n{path}",
        "fr": "Fichier introuvable :\n{path}", "pt": "Arquivo não encontrado:\n{path}", "zh": "找不到文件：\n{path}"},
    "confirm_close": {
        "en": "Transcriptions are running or queued: stop them?",
        "it": "Trascrizioni in corso o in coda: vuoi interromperle?",
        "es": "Hay transcripciones en curso o en cola: ¿quieres detenerlas?",
        "fr": "Des transcriptions sont en cours ou en attente : les interrompre ?",
        "pt": "Há transcrições em andamento ou na fila: deseja interrompê-las?",
        "zh": "有正在进行或排队的转写：要中止吗？"},
    "play": {"en": "Start", "it": "Avvia", "es": "Iniciar", "fr": "Lancer", "pt": "Iniciar", "zh": "开始"},
    "remove": {"en": "Remove", "it": "Togli", "es": "Quitar", "fr": "Retirer", "pt": "Remover", "zh": "移除"},
    # --- row and total status ---
    "status_error": {"en": "error", "it": "errore", "es": "error", "fr": "erreur", "pt": "erro", "zh": "错误"},
    "status_done": {
        "en": "done in {time}", "it": "fatto in {time}", "es": "hecho en {time}",
        "fr": "terminé en {time}", "pt": "concluído em {time}", "zh": "已完成，用时 {time}"},
    "status_estimating": {
        "en": "estimating{dots}", "it": "calcolo della stima{dots}", "es": "calculando la estimación{dots}",
        "fr": "calcul de l'estimation{dots}", "pt": "calculando a estimativa{dots}", "zh": "正在估算{dots}"},
    "status_queued": {
        "en": "queued (#{n}) · ETA {eta}", "it": "in coda ({n}°) · ETA {eta}", "es": "en cola (n.º {n}) · ETA {eta}",
        "fr": "en attente (n° {n}) · ETA {eta}", "pt": "na fila (n.º {n}) · ETA {eta}", "zh": "排队中（第 {n} 位）· 剩余 {eta}"},
    "status_waiting": {
        "en": "waiting · ETA {eta}", "it": "in attesa · ETA {eta}", "es": "en espera · ETA {eta}",
        "fr": "prête · ETA {eta}", "pt": "aguardando · ETA {eta}", "zh": "等待中 · 剩余 {eta}"},
    "status_running": {
        "en": "{stage} {pct} · ETA {eta}", "it": "{stage} {pct} · ETA {eta}", "es": "{stage} {pct} · ETA {eta}",
        "fr": "{stage} {pct} · ETA {eta}", "pt": "{stage} {pct} · ETA {eta}", "zh": "{stage} {pct} · 剩余 {eta}"},
    "total_done": {
        "en": "all done ({n} recordings)", "it": "tutto fatto ({n} registrazioni)", "es": "todo hecho ({n} grabaciones)",
        "fr": "tout est terminé ({n} enregistrements)", "pt": "tudo concluído ({n} gravações)", "zh": "全部完成（{n} 个录音）"},
    "total_estimating": {
        "en": "{n} to do · estimating{dots}", "it": "{n} da fare · calcolo della stima{dots}",
        "es": "{n} pendientes · calculando la estimación{dots}", "fr": "{n} à faire · calcul de l'estimation{dots}",
        "pt": "{n} a fazer · calculando a estimativa{dots}", "zh": "还剩 {n} 个 · 正在估算{dots}"},
    "total_eta": {
        "en": "{n} to do · total ETA {eta}", "it": "{n} da fare · ETA totale {eta}",
        "es": "{n} pendientes · ETA total {eta}", "fr": "{n} à faire · ETA totale {eta}",
        "pt": "{n} a fazer · ETA total {eta}", "zh": "还剩 {n} 个 · 总剩余时间 {eta}"},
    # --- stages ---
    "stage_start": {"en": "starting", "it": "avvio", "es": "iniciando", "fr": "démarrage", "pt": "iniciando", "zh": "启动中"},
    "stage_audio": {"en": "audio", "it": "audio", "es": "audio", "fr": "audio", "pt": "áudio", "zh": "音频"},
    "stage_video": {
        "en": "reading names", "it": "lettura nomi", "es": "leyendo nombres",
        "fr": "lecture des noms", "pt": "lendo nomes", "zh": "读取姓名"},
    "stage_diarization": {
        "en": "separating voices", "it": "separazione voci", "es": "separando voces",
        "fr": "séparation des voix", "pt": "separando vozes", "zh": "分离声音"},
    "stage_parallel": {
        "en": "names + voices", "it": "nomi + voci", "es": "nombres + voces",
        "fr": "noms + voix", "pt": "nomes + vozes", "zh": "姓名 + 声音"},
    "stage_asr": {
        "en": "transcribing", "it": "trascrizione", "es": "transcribiendo",
        "fr": "transcription", "pt": "transcrevendo", "zh": "转写"},
    "stage_content": {
        "en": "names from content", "it": "nomi dal contenuto", "es": "nombres del contenido",
        "fr": "noms du contenu", "pt": "nomes do conteúdo", "zh": "从内容识别姓名"},
    "stage_title": {"en": "title", "it": "titolo", "es": "título", "fr": "titre", "pt": "título", "zh": "标题"},
    "stage_fatto": {"en": "done", "it": "fatto", "es": "hecho", "fr": "terminé", "pt": "concluído", "zh": "完成"},
    # --- hardware ---
    "hw_fast": {
        "en": "GPU {name}: fast mode", "it": "GPU {name}: modalità veloce", "es": "GPU {name}: modo rápido",
        "fr": "GPU {name} : mode rapide", "pt": "GPU {name}: modo rápido", "zh": "GPU {name}：快速模式"},
    "hw_cpu": {
        "en": "{reason}: CPU mode (slower)", "it": "{reason}: modalità CPU (più lenta)",
        "es": "{reason}: modo CPU (más lento)", "fr": "{reason} : mode CPU (plus lent)",
        "pt": "{reason}: modo CPU (mais lento)", "zh": "{reason}：CPU 模式（较慢）"},
    "hw_no_torch": {
        "en": "PyTorch not available", "it": "PyTorch non disponibile", "es": "PyTorch no disponible",
        "fr": "PyTorch indisponible", "pt": "PyTorch indisponível", "zh": "PyTorch 不可用"},
    "hw_no_gpu": {
        "en": "No usable NVIDIA GPU", "it": "Nessuna GPU NVIDIA utilizzabile", "es": "Ninguna GPU NVIDIA utilizable",
        "fr": "Aucun GPU NVIDIA utilisable", "pt": "Nenhuma GPU NVIDIA utilizável", "zh": "没有可用的 NVIDIA GPU"},
    "hw_too_old": {
        "en": "{name} too old", "it": "{name} troppo vecchia", "es": "{name} demasiado antigua",
        "fr": "{name} trop ancien", "pt": "{name} antiga demais", "zh": "{name} 太旧"},
    "hw_low_memory": {
        "en": "{name}: not enough memory", "it": "{name}: memoria insufficiente", "es": "{name}: memoria insuficiente",
        "fr": "{name} : mémoire insuffisante", "pt": "{name}: memória insuficiente", "zh": "{name}：显存不足"},
    "hw_cpu_requested": {
        "en": "CPU requested", "it": "CPU richiesta", "es": "CPU solicitada",
        "fr": "CPU demandé", "pt": "CPU solicitada", "zh": "已指定 CPU"},
    # --- progress log ---
    "log_decoding": {
        "en": "Decoding audio...", "it": "Decodifica audio...", "es": "Decodificando el audio...",
        "fr": "Décodage de l'audio...", "pt": "Decodificando o áudio...", "zh": "正在解码音频..."},
    "log_reading_names": {
        "en": "Reading names from the video ({fps} fps)...", "it": "Lettura dei nomi dal video ({fps} fps)...",
        "es": "Leyendo los nombres del vídeo ({fps} fps)...", "fr": "Lecture des noms dans la vidéo ({fps} fps)...",
        "pt": "Lendo os nomes do vídeo ({fps} fps)...", "zh": "正在从视频读取姓名（{fps} fps）..."},
    "log_video_read": {
        "en": "  video read in {s}s", "it": "  video letto in {s}s", "es": "  vídeo leído en {s}s",
        "fr": "  vidéo lue en {s}s", "pt": "  vídeo lido em {s}s", "zh": "  视频读取完成，用时 {s} 秒"},
    "log_separating": {
        "en": "Separating voices (pyannote)...", "it": "Separazione delle voci (pyannote)...",
        "es": "Separando las voces (pyannote)...", "fr": "Séparation des voix (pyannote)...",
        "pt": "Separando as vozes (pyannote)...", "zh": "正在分离声音（pyannote）..."},
    "log_separated": {
        "en": "  voices separated in {s}s: {n} voices", "it": "  voci separate in {s}s: {n} voci",
        "es": "  voces separadas en {s}s: {n} voces", "fr": "  voix séparées en {s}s : {n} voix",
        "pt": "  vozes separadas em {s}s: {n} vozes", "zh": "  声音分离完成，用时 {s} 秒：{n} 个声音"},
    "log_names": {
        "en": "Names read from the video: {names}", "it": "Nomi letti dal video: {names}",
        "es": "Nombres leídos del vídeo: {names}", "fr": "Noms lus dans la vidéo : {names}",
        "pt": "Nomes lidos do vídeo: {names}", "zh": "从视频读取的姓名：{names}"},
    "log_no_labels": {
        "en": "No highlighted Teams label in the video.", "it": "Nessuna etichetta Teams evidenziata nel video.",
        "es": "Ninguna etiqueta de Teams resaltada en el vídeo.",
        "fr": "Aucune étiquette Teams mise en évidence dans la vidéo.",
        "pt": "Nenhuma etiqueta do Teams destacada no vídeo.", "zh": "视频中没有高亮的 Teams 标签。"},
    "log_no_pyannote_error": {
        "en": "pyannote model not available: HF_TOKEN is needed in the .env file (see the guide).",
        "it": "Modello pyannote non disponibile: serve HF_TOKEN nel file .env (vedi la guida).",
        "es": "Modelo pyannote no disponible: hace falta HF_TOKEN en el archivo .env (consulta la guía).",
        "fr": "Modèle pyannote indisponible : HF_TOKEN est nécessaire dans le fichier .env (voir le guide).",
        "pt": "Modelo pyannote indisponível: é necessário HF_TOKEN no arquivo .env (veja o guia).",
        "zh": "pyannote 模型不可用：需要在 .env 文件中设置 HF_TOKEN（请参阅指南）。"},
    "log_no_pyannote_warning": {
        "en": "WARNING: pyannote model not available, speakers are assigned from the video only (less accurate).",
        "it": "ATTENZIONE: modello pyannote non disponibile, attribuisco gli speaker solo dal video (meno preciso).",
        "es": "AVISO: modelo pyannote no disponible, los hablantes se asignan solo a partir del vídeo (menos preciso).",
        "fr": "ATTENTION : modèle pyannote indisponible, les intervenants sont attribués d'après la vidéo seule (moins précis).",
        "pt": "AVISO: modelo pyannote indisponível, os oradores são atribuídos apenas a partir do vídeo (menos preciso).",
        "zh": "警告：pyannote 模型不可用，只根据视频判断说话人（准确度较低）。"},
    "log_downloading_model": {
        "en": "Downloading the Whisper model {model} (1.6-3 GB, first time only)...",
        "it": "Scarico il modello Whisper {model} (1,6-3 GB, solo la prima volta)...",
        "es": "Descargando el modelo Whisper {model} (1,6-3 GB, solo la primera vez)...",
        "fr": "Téléchargement du modèle Whisper {model} (1,6-3 Go, la première fois seulement)...",
        "pt": "Baixando o modelo Whisper {model} (1,6-3 GB, só na primeira vez)...",
        "zh": "正在下载 Whisper 模型 {model}（1.6-3 GB，仅首次）..."},
    "log_transcribing": {
        "en": "Transcribing ({model}, {device}, {language})...", "it": "Trascrizione ({model}, {device}, {language})...",
        "es": "Transcribiendo ({model}, {device}, {language})...", "fr": "Transcription ({model}, {device}, {language})...",
        "pt": "Transcrevendo ({model}, {device}, {language})...", "zh": "正在转写（{model}，{device}，{language}）..."},
    "log_transcribed": {
        "en": "  transcribed in {s}s", "it": "  trascrizione fatta in {s}s", "es": "  transcripción hecha en {s}s",
        "fr": "  transcription terminée en {s}s", "pt": "  transcrição concluída em {s}s", "zh": "  转写完成，用时 {s} 秒"},
    "log_detected": {
        "en": "  detected language: {language}", "it": "  lingua rilevata: {language}",
        "es": "  idioma detectado: {language}", "fr": "  langue détectée : {language}",
        "pt": "  idioma detectado: {language}", "zh": "  检测到的语言：{language}"},
    "log_lag": {
        "en": "Estimated Teams highlight delay: {lag}s", "it": "Ritardo evidenziazione Teams stimato: {lag}s",
        "es": "Retraso estimado del resaltado de Teams: {lag}s", "fr": "Retard estimé de la mise en évidence Teams : {lag}s",
        "pt": "Atraso estimado do destaque do Teams: {lag}s", "zh": "估计的 Teams 高亮延迟：{lag} 秒"},
    "log_library": {
        "en": "Voice library updated: {names}", "it": "Libreria voci aggiornata: {names}",
        "es": "Biblioteca de voces actualizada: {names}", "fr": "Bibliothèque de voix mise à jour : {names}",
        "pt": "Biblioteca de vozes atualizada: {names}", "zh": "声纹库已更新：{names}"},
    "log_lm_download": {
        "en": "Downloading the language model ({gb} GB, first time only)...",
        "it": "Scarico il modello linguistico ({gb} GB, solo la prima volta)...",
        "es": "Descargando el modelo de lenguaje ({gb} GB, solo la primera vez)...",
        "fr": "Téléchargement du modèle de langue ({gb} Go, la première fois seulement)...",
        "pt": "Baixando o modelo de linguagem ({gb} GB, só na primeira vez)...",
        "zh": "正在下载语言模型（{gb} GB，仅首次）..."},
    "log_lm_failed": {
        "en": "  language model not available ({error}): names from content and title skipped",
        "it": "  modello linguistico non disponibile ({error}): niente nomi dal contenuto né titolo",
        "es": "  modelo de lenguaje no disponible ({error}): sin nombres del contenido ni título",
        "fr": "  modèle de langue indisponible ({error}) : ni noms du contenu ni titre",
        "pt": "  modelo de linguagem indisponível ({error}): sem nomes do conteúdo nem título",
        "zh": "  语言模型不可用（{error}）：跳过从内容识别姓名和标题"},
    "log_content": {
        "en": "Recognising speakers from what they say ({device})...",
        "it": "Riconoscimento di chi parla da quello che dice ({device})...",
        "es": "Reconociendo a los hablantes por lo que dicen ({device})...",
        "fr": "Reconnaissance des intervenants d'après ce qu'ils disent ({device})...",
        "pt": "Reconhecendo quem fala pelo que diz ({device})...",
        "zh": "正在根据发言内容识别说话人（{device}）..."},
    "log_content_done": {
        "en": "  {n} names found in {s}s", "it": "  {n} nomi trovati in {s}s", "es": "  {n} nombres encontrados en {s}s",
        "fr": "  {n} noms trouvés en {s}s", "pt": "  {n} nomes encontrados em {s}s", "zh": "  找到 {n} 个姓名，用时 {s} 秒"},
    "log_title": {
        "en": "Meeting title: {title}", "it": "Titolo della riunione: {title}", "es": "Título de la reunión: {title}",
        "fr": "Titre de la réunion : {title}", "pt": "Título da reunião: {title}", "zh": "会议标题：{title}"},
    "log_rename_failed": {
        "en": "  the folder keeps its name: {error}", "it": "  la cartella resta col suo nome: {error}",
        "es": "  la carpeta conserva su nombre: {error}", "fr": "  le dossier garde son nom : {error}",
        "pt": "  a pasta mantém o nome: {error}", "zh": "  文件夹保留原名：{error}"},
    "log_done": {
        "en": "Done in {s}s -> {path}", "it": "Fatto in {s}s -> {path}", "es": "Hecho en {s}s -> {path}",
        "fr": "Terminé en {s}s -> {path}", "pt": "Concluído em {s}s -> {path}", "zh": "完成，用时 {s} 秒 -> {path}"},
    # --- meeting languages, named in the interface language ---
    "lang_auto": {
        "en": "Detect automatically", "it": "Rilevamento automatico", "es": "Detección automática",
        "fr": "Détection automatique", "pt": "Detecção automática", "zh": "自动检测"},
    "lang_it": {"en": "Italian", "it": "Italiano", "es": "Italiano", "fr": "Italien", "pt": "Italiano", "zh": "意大利语"},
    "lang_en": {"en": "English", "it": "Inglese", "es": "Inglés", "fr": "Anglais", "pt": "Inglês", "zh": "英语"},
    "lang_es": {"en": "Spanish", "it": "Spagnolo", "es": "Español", "fr": "Espagnol", "pt": "Espanhol", "zh": "西班牙语"},
    "lang_fr": {"en": "French", "it": "Francese", "es": "Francés", "fr": "Français", "pt": "Francês", "zh": "法语"},
    "lang_pt": {"en": "Portuguese", "it": "Portoghese", "es": "Portugués", "fr": "Portugais", "pt": "Português", "zh": "葡萄牙语"},
    "lang_zh": {"en": "Chinese", "it": "Cinese", "es": "Chino", "fr": "Chinois", "pt": "Chinês", "zh": "中文"},
}

_settings: dict | None = None


def _load() -> dict:
    global _settings
    if _settings is None:
        try:
            _settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _settings = {}
    return _settings


def _save():
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS.write_text(json.dumps(_load(), indent=1), encoding="utf-8")
    except OSError:
        pass  # a read-only data folder only costs remembering the choice


def system_language() -> str:
    """The two-letter code of the system's display language ("" if unknown)."""
    if sys.platform == "win32":
        try:
            import ctypes

            name = locale.windows_locale.get(ctypes.windll.kernel32.GetUserDefaultUILanguage(), "")
            return name.split("_")[0].lower()
        except Exception:
            return ""
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        value = os.environ.get(var, "")
        if value and value not in ("C", "POSIX"):
            return value.split(":")[0].split("_")[0].split(".")[0].lower()
    return ""


def ui_language() -> str:
    code = _load().get("ui_language") or system_language()
    return code if code in UI_LANGUAGES else "en"


def set_ui_language(code: str):
    if code in UI_LANGUAGES:
        _load()["ui_language"] = code
        _save()


def meeting_language() -> str:
    """Language of the meetings: the saved choice, automatic detection until one is made."""
    code = _load().get("meeting_language")
    return code if code in MEETING_LANGUAGES else "auto"


def set_meeting_language(code: str):
    if code in MEETING_LANGUAGES:
        _load()["meeting_language"] = code
        _save()


def setting(key: str, default):
    """Another saved choice of the window (names from content, folder name)."""
    value = _load().get(key, default)
    return value if isinstance(value, type(default)) else default


def set_setting(key: str, value):
    _load()[key] = value
    _save()


def t(key: str, lang: str | None = None, **values) -> str:
    """The text for key in lang (default: the interface language), English if missing."""
    texts = T[key]
    text = texts.get(lang or ui_language()) or texts["en"]
    return text.format(dots=DOTS, **values)


def language_name(code: str, lang: str | None = None) -> str:
    """A meeting language's name in the interface language ("auto" included)."""
    key = f"lang_{code}"
    return t(key, lang) if key in T else code
