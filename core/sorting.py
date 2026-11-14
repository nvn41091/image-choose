from core.data_store import Photo

SORT_OPTIONS = (
    ('name_asc', 'Tên ảnh: A → Z'),
    ('name_desc', 'Tên ảnh: Z → A'),
    ('score_desc', 'Điểm: cao → thấp'),
    ('score_asc', 'Điểm: thấp → cao'),
    ('stars_desc', 'Số sao: nhiều → ít'),
    ('stars_asc', 'Số sao: ít → nhiều'),
)


def photo_sort_key(path: str, photo: Photo, mode: str):
    name = (path.casefold(), path)
    if mode.startswith('score_'):
        value = photo.ai_score
    elif mode.startswith('stars_'):
        value = photo.stars or None
    else:
        return name
    # 0 điểm là một kết quả hợp lệ; None/0 sao nghĩa là chưa được đánh giá.
    return (value is None, -(value or 0) if mode.endswith('_desc') else value or 0, *name)
