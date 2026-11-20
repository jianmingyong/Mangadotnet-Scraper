import asyncio
import logging
import sys

if sys.platform == "linux":
    import uvloop

from mangadotnet_scraper.app import App


def initialize() -> None:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        filename="mangadotnet_scraper.log",
        encoding="utf-8",
    )

    try:
        if sys.platform == "linux":
            uvloop.run(initialize_app())
        else:
            asyncio.run(initialize_app())
    except Exception:
        logging.getLogger(__name__).exception("Unhandled exception caught")
        raise


async def initialize_app() -> None:
    async with App() as app:
        await app.run()


# async def upload_chapters(
#     module: BaseModule,
#     config: MangaDotNetScraperConfig,
#     data: MangaDotNetScraperData,
#     mangadotnet_api: MangaDotNetApi,
# ):
#     total_progress = Progress(
#         TextColumn("Upload {task.description} Overall"),
#         BarColumn(bar_width=None),
#         MofNCompleteColumn(),
#     )
#     current_progress_title = Progress(
#         TextColumn("{task.fields[status]} ({task.fields[count]})")
#     )

#     current_progress = Progress(
#         SpinnerColumn(),
#         TextColumn(
#             "[{task.fields[chapter]}] {task.fields[status]}", markup=False
#         ),
#         BarColumn(),
#         TaskProgressColumn(),
#         DownloadColumn(),
#         TransferSpeedColumn(),
#         TimeRemainingColumn(),
#     )

#     group_id_cache: dict[str, int] = {}

#     with Live(
#         Group(
#             Rule(),
#             total_progress,
#             Rule(),
#             current_progress_title,
#             current_progress,
#         ),
#         transient=True,
#     ):
#         manga_count, manga = data.get_non_uploaded_manga(module.module_id)
#         total_progress_task = total_progress.add_task(
#             module.display_name, total=manga_count
#         )
#         current_progress_title_task = current_progress_title.add_task(
#             "", status="", count=0
#         )

#         for rowid, manga_id, link, title, mangadotnet_id in manga:
#             current_progress_title.update(
#                 current_progress_title_task,
#                 status=f"Uploading: {title}",
#                 count=0,
#             )

#             chapters_count, chapters = data.get_non_uploaded_chapters(rowid)

#             current_progress_title.update(
#                 current_progress_title_task, count=chapters_count
#             )

#             chapters = [
#                 (
#                     manga_rowid,
#                     language,
#                     scanlator_group,
#                     type,
#                     chapter_number,
#                     volume_number,
#                     chapter_title,
#                     link,
#                     chapter_id,
#                 )
#                 for manga_rowid, language, scanlator_group, type, chapter_number, volume_number, chapter_title, link, chapter_id in chapters
#             ]

#             upload_semaphore = Semaphore(module.upload_concurrency)

#             async def upload_chapter_task(
#                 upload_semaphore: Semaphore,
#                 mangadotnet_id: int,
#                 manga_rowid: int,
#                 language: str,
#                 scanlator_group: str,
#                 type: str,
#                 chapter_number: float | None,
#                 volume_number: float | None,
#                 chapter_title: str,
#                 chapter_link: str,
#                 manga_link: str,
#                 manga_id: str,
#                 chapter_id: str,
#             ) -> None:
#                 async with upload_semaphore:
#                     task_id = current_progress.add_task(
#                         "",
#                         start=False,
#                         total=None,
#                         chapter=f"{mangadotnet_id}:{language}:{chapter_number} [{scanlator_group}]",
#                         status="Fetching Manga Pages...",
#                     )

#                     try:
#                         pages = await module.fetch_manga_pages(
#                             manga_id, manga_link, chapter_id, chapter_link
#                         )
#                         pages_count = len(pages)

#                         if len(pages) == 0:
#                             logging.getLogger().info(
#                                 f"Fetch Failure [{manga_rowid}]: {mangadotnet_id}:{language}:{chapter_number} {chapter_title} [{scanlator_group}]"
#                             )
#                             return

#                         current_progress.update(
#                             task_id,
#                             total=pages_count,
#                             status="Downloading Image",
#                         )

#                         zip_buffer = BytesIO()
#                         has_error = False

#                         with ZipFile(
#                             zip_buffer, "a", ZIP_DEFLATED, compresslevel=9
#                         ) as zip_file:
#                             download_semaphore = Semaphore(
#                                 module.download_concurrency
#                             )

#                             async def download_image_task(page) -> None:
#                                 async with download_semaphore:
#                                     image = await module.fetch_manga_image(
#                                         page
#                                     )
#                                     zip_file.writestr(
#                                         image.filename, image.data
#                                     )
#                                     current_progress.advance(task_id)

#                             try:
#                                 async with TaskGroup() as group:
#                                     for page in pages:
#                                         group.create_task(
#                                             download_image_task(page)
#                                         )
#                             except* FetchError:
#                                 has_error = True

#                         if has_error:
#                             logging.getLogger().info(
#                                 f"Download Failure [{manga_rowid}]: {mangadotnet_id}:{language}:{chapter_number} {chapter_title} [{scanlator_group}]"
#                             )
#                             return

#                         zip_file_size = zip_buffer.tell()

#                         current_progress.update(
#                             task_id,
#                             completed=0,
#                             total=zip_file_size,
#                             status="Preparing Upload (1)",
#                         )

#                         group_id = group_id_cache.get(scanlator_group)

#                         if group_id is None:
#                             groups = await mangadotnet_api.get_group_ids(
#                                 scanlator_group
#                             )
#                             for group in groups["groups"]:
#                                 if group["name"] == scanlator_group:
#                                     group_id = group["id"]
#                                     group_id_cache[scanlator_group] = group[
#                                         "id"
#                                     ]
#                                     break

#                         if group_id is None:
#                             return

#                         if type != "chapter" and type != "volume":
#                             return

#                         current_progress.update(
#                             task_id,
#                             completed=0,
#                             total=zip_file_size,
#                             status="Preparing Upload (2)",
#                         )

#                         try:
#                             location = await mangadotnet_api.prepare_upload(
#                                 zip_file_size,
#                                 MangaDotNetApi.MangaDotNetTusUploadMetadata(
#                                     mangadotnet_id,
#                                     chapter_number,
#                                     volume_number,
#                                     language,
#                                     chapter_title,
#                                     [group_id],
#                                     None,
#                                     None,
#                                     type,
#                                     None,
#                                     None,
#                                 ),
#                             )
#                         except ClientResponseError as error:
#                             if error.code == 409:
#                                 logging.getLogger().info(
#                                     f"Upload Skipped (Already Uploaded): [{manga_rowid}] {mangadotnet_id}:{language}:{chapter_number} {chapter_title} [{scanlator_group}]"
#                                 )
#                                 data.mark_chapter_uploaded(
#                                     manga_rowid,
#                                     language,
#                                     scanlator_group,
#                                     type,
#                                     chapter_number,
#                                     volume_number,
#                                 )
#                             return

#                         def callable_progress(current):
#                             current_progress.update(
#                                 task_id, completed=current, status="Uploading"
#                             )

#                         current_progress.start_task(task_id)
#                         current_progress.update(task_id, status="Uploading")

#                         success = await mangadotnet_api.upload_file(
#                             location, zip_buffer, callable_progress
#                         )

#                         current_progress.stop_task(task_id)
#                         current_progress.update(
#                             task_id, total=None, status="Verify Upload (0s)"
#                         )

#                         if not success:
#                             return

#                         found = False
#                         start_check = monotonic()

#                         while True:
#                             uploaded_mangas = (
#                                 await mangadotnet_api.get_uploaded_manga(
#                                     mangadotnet_id
#                                 )
#                             )

#                             for uploaded_manga in uploaded_mangas["uploads"]:
#                                 if (
#                                     type == "chapter"
#                                     and chapter_number is not None
#                                     and uploaded_manga["manga_id"]
#                                     == mangadotnet_id
#                                     and uploaded_manga["language"] == language
#                                     and uploaded_manga["chapter_number"]
#                                     is not None
#                                     and abs(
#                                         uploaded_manga["chapter_number"]
#                                         - chapter_number
#                                     )
#                                     < 0.1
#                                     and any(
#                                         uploaded_group["id"] == group_id
#                                         for uploaded_group in uploaded_manga[
#                                             "groups"
#                                         ]
#                                     )
#                                     and uploaded_manga["type"] == "chapter"
#                                     and (
#                                         uploaded_manga["status"] == "pending"
#                                         or uploaded_manga["status"]
#                                         == "approved"
#                                     )
#                                 ):
#                                     # Upload Success
#                                     found = True
#                                     break

#                             if found:
#                                 break

#                             await sleep(1)

#                             duration = monotonic() - start_check
#                             current_progress.update(
#                                 task_id,
#                                 status=f"Verify Upload ({duration:.0f}s)",
#                             )

#                             if duration > config.upload_verify_duration:
#                                 break

#                         if found:
#                             data.mark_chapter_uploaded(
#                                 manga_rowid,
#                                 language,
#                                 scanlator_group,
#                                 type,
#                                 chapter_number,
#                                 volume_number,
#                             )
#                             logging.getLogger().info(
#                                 f"Upload Success: [{manga_rowid}] {mangadotnet_id}:{language}:{chapter_number} {chapter_title} [{scanlator_group}]"
#                             )
#                         else:
#                             logging.getLogger().info(
#                                 f"Upload Failure [{manga_rowid}]: {mangadotnet_id}:{language}:{chapter_number} {chapter_title} [{scanlator_group}]"
#                             )
#                     except Exception:
#                         logging.getLogger().exception(
#                             f"Upload Failure [{manga_rowid}]: {mangadotnet_id}:{language}:{chapter_number} {chapter_title} [{scanlator_group}]"
#                         )
#                     finally:
#                         current_progress.remove_task(task_id)

#             try:
#                 async with TaskGroup() as group:
#                     for (
#                         manga_rowid,
#                         language,
#                         scanlator_group,
#                         type,
#                         chapter_number,
#                         volume_number,
#                         chapter_title,
#                         chapter_link,
#                         chapter_id,
#                     ) in chapters:
#                         group.create_task(
#                             upload_chapter_task(
#                                 upload_semaphore,
#                                 mangadotnet_id,
#                                 manga_rowid,
#                                 language,
#                                 scanlator_group,
#                                 type,
#                                 chapter_number,
#                                 volume_number,
#                                 chapter_title,
#                                 chapter_link,
#                                 link,
#                                 manga_id,
#                                 chapter_id,
#                             )
#                         )
#             except* Exception as error:
#                 logging.getLogger().exception(error.message)

#             total_progress.advance(total_progress_task)

#         total_progress.print(f"Done upload {module.display_name}")
