import os
import uuid
import requests
import json
import re
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from mutagen import File
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TYER, USLT, APIC, TDRC, delete, COMM
from mutagen.mp3 import MP3
from mutagen.flac import FLAC, Picture
from mutagen.oggvorbis import OggVorbis
from mutagen.mp4 import MP4
from mutagen.wave import WAVE
from mutagen.aiff import AIFF
from urllib.parse import urlparse
import tempfile
import threading
import time
import logging
import mimetypes
import traceback
import shutil
import signal
import atexit
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 全局变量
app = Flask(__name__)
CORS(app)
TEMP_DIR = tempfile.gettempdir()
FILE_CLEANUP_TIME = 300  # 5分钟
file_registry = {}
is_shutting_down = False
logger = logging.getLogger(__name__)

# 创建线程池执行器
download_executor = ThreadPoolExecutor(max_workers=10)
metadata_executor = ThreadPoolExecutor(max_workers=5)

# 创建带有重试机制的会话
def create_session():
    """创建带有重试机制的请求会话"""
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=100, pool_maxsize=100)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

# 全局会话对象
download_session = create_session()

def safe_json_parse(json_string):
    """安全地解析JSON，处理控制字符和换行符"""
    try:
        return json.loads(json_string)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON解析失败，尝试清理无效字符: {e}")
        
        # 清理无效的控制字符（保留\t, \n, \r）
        cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', json_string)
        
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e2:
            logger.error(f"清理后仍然无法解析JSON: {e2}")
            raise

def download_file_chunk(url, start_byte, end_byte, chunk_file_path):
    """下载文件的指定分块"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': '*/*',
            'Accept-Encoding': 'identity',
            'Range': f'bytes={start_byte}-{end_byte}'
        }
        
        response = download_session.get(url, headers=headers, stream=True, timeout=30)
        response.raise_for_status()
        
        with open(chunk_file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        return True
    except Exception as e:
        logger.error(f"下载分块失败: {e}")
        return False

def download_file_parallel(url, file_path, num_threads=8):
    """多线程并行下载文件"""
    try:
        logger.info(f"开始多线程下载: {url}")
        
        # 获取文件大小
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': '*/*'
        }
        
        response = download_session.head(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        file_size = int(response.headers.get('content-length', 0))
        
        if file_size == 0:
            # 如果不支持HEAD或无法获取大小，回退到单线程下载
            logger.warning("无法获取文件大小，使用单线程下载")
            return download_file_single(url, file_path)
        
        logger.info(f"文件大小: {file_size} bytes, 使用 {num_threads} 个线程下载")
        
        # 计算每个线程下载的字节范围
        chunk_size = file_size // num_threads
        ranges = []
        
        for i in range(num_threads):
            start_byte = i * chunk_size
            end_byte = start_byte + chunk_size - 1 if i < num_threads - 1 else file_size - 1
            ranges.append((start_byte, end_byte))
        
        # 临时分块文件列表
        chunk_files = []
        futures = []
        
        # 使用线程池并行下载分块
        for i, (start_byte, end_byte) in enumerate(ranges):
            chunk_file_path = f"{file_path}.part{i}"
            chunk_files.append(chunk_file_path)
            
            future = download_executor.submit(
                download_file_chunk, url, start_byte, end_byte, chunk_file_path
            )
            futures.append(future)
        
        # 等待所有分块下载完成
        for future in as_completed(futures):
            if not future.result():
                logger.error("某个分块下载失败")
                # 清理已下载的分块
                for chunk_file in chunk_files:
                    if os.path.exists(chunk_file):
                        os.remove(chunk_file)
                return False
        
        # 合并分块文件
        logger.info("开始合并分块文件")
        with open(file_path, 'wb') as output_file:
            for chunk_file in chunk_files:
                with open(chunk_file, 'rb') as input_file:
                    shutil.copyfileobj(input_file, output_file)
                # 删除临时分块文件
                os.remove(chunk_file)
        
        logger.info(f"下载完成: {file_path}, 文件大小: {os.path.getsize(file_path)} bytes")
        return True
        
    except Exception as e:
        logger.error(f"多线程下载失败: {e}")
        # 清理可能存在的分块文件
        for i in range(num_threads):
            chunk_file = f"{file_path}.part{i}"
            if os.path.exists(chunk_file):
                os.remove(chunk_file)
        return False

def download_file_single(url, file_path):
    """单线程下载文件（备用方案）"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': '*/*',
            'Accept-Encoding': 'identity',
            'Connection': 'keep-alive'
        }
        
        logger.info(f"开始单线程下载: {url}")
        response = download_session.get(url, stream=True, headers=headers, timeout=60)
        response.raise_for_status()
        
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        logger.info(f"单线程下载完成: {file_path}, 文件大小: {os.path.getsize(file_path)} bytes")
        return True
        
    except Exception as e:
        logger.error(f"单线程下载失败: {e}")
        return False

def download_file(url, file_path):
    """下载文件到指定路径（自动选择多线程或单线程）"""
    # 尝试多线程下载，如果失败则回退到单线程
    if not download_file_parallel(url, file_path):
        logger.warning("多线程下载失败，尝试单线程下载")
        return download_file_single(url, file_path)
    return True

def download_cover(cover_url):
    """下载封面图片"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        logger.info(f"开始下载封面: {cover_url}")
        response = download_session.get(cover_url, headers=headers, timeout=30)
        response.raise_for_status()
        logger.info("封面下载成功")
        return response.content
    except Exception as e:
        logger.error(f"封面下载失败: {e}")
        return None

def strip_existing_metadata(file_path):
    """删除文件中的所有现有元数据"""
    try:
        logger.info(f"开始清理现有元数据: {file_path}")
        
        # 检测文件类型
        file_ext = os.path.splitext(file_path)[1].lower()
        
        if file_ext == '.mp3':
            try:
                delete(file_path)
                logger.info("MP3 ID3标签删除成功")
            except Exception as e:
                logger.warning(f"删除MP3标签时出错: {e}")
                try:
                    audio = MP3(file_path)
                    if audio.tags:
                        audio.delete()
                        audio.save()
                except:
                    pass
            
        elif file_ext == '.flac':
            try:
                audio = FLAC(file_path)
                audio.clear()
                audio.save()
                logger.info("FLAC标签清除成功")
            except Exception as e:
                logger.warning(f"清除FLAC标签时出错: {e}")
            
        elif file_ext in ['.ogg', '.oga']:
            try:
                audio = OggVorbis(file_path)
                audio.delete()
                audio.save()
                logger.info("OGG标签清除成功")
            except Exception as e:
                logger.warning(f"清除OGG标签时出错: {e}")
            
        elif file_ext in ['.m4a', '.mp4']:
            try:
                audio = MP4(file_path)
                audio.delete()
                audio.save()
                logger.info("MP4标签清除成功")
            except Exception as e:
                logger.warning(f"清除MP4标签时出错: {e}")
            
        elif file_ext == '.wav':
            try:
                audio = WAVE(file_path)
                if hasattr(audio, 'tags') and audio.tags:
                    audio.delete()
                    audio.save()
                logger.info("WAV标签清除成功")
            except Exception as e:
                logger.warning(f"清除WAV标签时出错: {e}")
                
        elif file_ext == '.aiff':
            try:
                audio = AIFF(file_path)
                if hasattr(audio, 'tags') and audio.tags:
                    audio.delete()
                    audio.save()
                logger.info("AIFF标签清除成功")
            except Exception as e:
                logger.warning(f"清除AIFF标签时出错: {e}")
        
        logger.info("现有元数据清理完成")
        return True
        
    except Exception as e:
        logger.error(f"清理元数据失败: {e}")
        logger.error(traceback.format_exc())
        return False

def add_metadata_to_mp3(file_path, metadata):
    """向MP3文件添加元数据"""
    try:
        logger.info(f"开始处理MP3文件: {file_path}")
        
        # 确保彻底删除现有标签
        try:
            delete(file_path)
        except:
            pass
        
        # 重新加载文件
        audio = MP3(file_path)
        
        # 检查是否还有标签，如果有则删除
        if audio.tags:
            audio.delete()
            audio.save()
        
        # 重新加载确保没有标签
        audio = MP3(file_path)
        
        # 添加新标签
        audio.add_tags()
        tags = audio.tags
        
        encoding = 3  # UTF-8编码
        
        # 设置基本元数据
        if metadata.get('title'):
            tags.add(TIT2(encoding=encoding, text=metadata['title']))
        if metadata.get('artist'):
            tags.add(TPE1(encoding=encoding, text=metadata['artist']))
        if metadata.get('album'):
            tags.add(TALB(encoding=encoding, text=metadata['album']))
        if metadata.get('year'):
            year_str = str(metadata['year'])
            if year_str:
                tags.add(TDRC(encoding=encoding, text=year_str))
        
        # 添加歌词
        if metadata.get('lyrics'):
            tags.add(USLT(encoding=encoding, lang='eng', desc='Lyrics', text=metadata['lyrics']))
        
        # 添加注释
        if metadata.get('tips'):
            tags.add(COMM(encoding=encoding, lang='eng', desc='Comment', text=metadata['tips']))
        
        # 添加封面
        if metadata.get('cover_data'):
            cover_data = metadata['cover_data']
            # 检测MIME类型
            mime_type = 'image/jpeg'
            if cover_data.startswith(b'\x89PNG'):
                mime_type = 'image/png'
            
            tags.add(APIC(
                encoding=encoding,
                mime=mime_type,
                type=3,
                desc='Cover',
                data=cover_data
            ))
        
        audio.save(v2_version=3)
        logger.info("MP3元数据添加成功")
        return True
        
    except Exception as e:
        logger.error(f"添加MP3元数据失败: {e}")
        logger.error(traceback.format_exc())
        return False

def add_metadata_to_flac(file_path, metadata):
    """向FLAC文件添加元数据"""
    try:
        logger.info(f"开始处理FLAC文件: {file_path}")
        audio = FLAC(file_path)
        
        # 清除现有标签
        audio.clear()
        
        # 设置基本元数据
        if metadata.get('title'):
            audio['title'] = [metadata['title']]
        if metadata.get('artist'):
            audio['artist'] = [metadata['artist']]
        if metadata.get('album'):
            audio['album'] = [metadata['album']]
        if metadata.get('year'):
            audio['date'] = [str(metadata['year'])]
        
        # 添加歌词
        if metadata.get('lyrics'):
            audio['lyrics'] = [metadata['lyrics']]
        
        # 添加注释
        if metadata.get('tips'):
            audio['comment'] = [metadata['tips']]
        
        # 添加封面
        if metadata.get('cover_data'):
            cover_data = metadata['cover_data']
            picture = Picture()
            picture.type = 3
            picture.mime = 'image/jpeg'
            picture.desc = 'Cover'
            picture.data = cover_data
            
            audio.clear_pictures()
            audio.add_picture(picture)
        
        audio.save()
        logger.info("FLAC元数据添加成功")
        return True
        
    except Exception as e:
        logger.error(f"添加FLAC元数据失败: {e}")
        logger.error(traceback.format_exc())
        return False

def add_metadata_to_ogg(file_path, metadata):
    """向OGG文件添加元数据"""
    try:
        logger.info(f"开始处理OGG文件: {file_path}")
        audio = OggVorbis(file_path)
        
        # 清除现有标签
        audio.delete()
        
        # 设置基本元数据 - 使用列表格式
        if metadata.get('title'):
            audio['title'] = [metadata['title']]
        if metadata.get('artist'):
            audio['artist'] = [metadata['artist']]
        if metadata.get('album'):
            audio['album'] = [metadata['album']]
        if metadata.get('year'):
            audio['date'] = [str(metadata['year'])]
        if metadata.get('lyrics'):
            audio['lyrics'] = [metadata['lyrics']]
        if metadata.get('tips'):
            audio['comment'] = [metadata['tips']]
        
        audio.save()
        logger.info("OGG元数据添加成功")
        return True
        
    except Exception as e:
        logger.error(f"添加OGG元数据失败: {e}")
        logger.error(traceback.format_exc())
        return False

def add_metadata_to_mp4(file_path, metadata):
    """向MP4文件添加元数据"""
    try:
        logger.info(f"开始处理MP4文件: {file_path}")
        audio = MP4(file_path)
        
        # 清除现有标签
        audio.delete()
        
        # MP4标签映射
        tag_map = {
            'title': '\xa9nam',
            'artist': '\xa9ART',
            'album': '\xa9alb',
            'year': '\xa9day',
            'lyrics': '\xa9lyr',
            'tips': '\xa9cmt'
        }
        
        # 设置基本元数据
        if metadata.get('title'):
            audio[tag_map['title']] = [metadata['title']]
        if metadata.get('artist'):
            audio[tag_map['artist']] = [metadata['artist']]
        if metadata.get('album'):
            audio[tag_map['album']] = [metadata['album']]
        if metadata.get('year'):
            audio[tag_map['year']] = [str(metadata['year'])]
        if metadata.get('lyrics'):
            audio[tag_map['lyrics']] = [metadata['lyrics']]
        if metadata.get('tips'):
            audio[tag_map['tips']] = [metadata['tips']]
        
        # 添加封面
        if metadata.get('cover_data'):
            cover_data = metadata['cover_data']
            audio['covr'] = [MP4.Cover(cover_data)]
        
        audio.save()
        logger.info("MP4元数据添加成功")
        return True
        
    except Exception as e:
        logger.error(f"添加MP4元数据失败: {e}")
        logger.error(traceback.format_exc())
        return False

def add_metadata_to_wav(file_path, metadata):
    """向WAV文件添加元数据"""
    try:
        logger.info(f"开始处理WAV文件: {file_path}")
        audio = WAVE(file_path)
        
        # WAV文件通常使用ID3标签
        if not audio.tags:
            audio.add_tags()
        
        encoding = 3  # UTF-8编码
        
        # 设置基本元数据
        if metadata.get('title'):
            audio.tags['TIT2'] = TIT2(encoding=encoding, text=metadata['title'])
        if metadata.get('artist'):
            audio.tags['TPE1'] = TPE1(encoding=encoding, text=metadata['artist'])
        if metadata.get('album'):
            audio.tags['TALB'] = TALB(encoding=encoding, text=metadata['album'])
        if metadata.get('year'):
            audio.tags['TDRC'] = TDRC(encoding=encoding, text=str(metadata['year']))
        if metadata.get('lyrics'):
            audio.tags['USLT'] = USLT(encoding=encoding, lang='eng', desc='Lyrics', text=metadata['lyrics'])
        if metadata.get('tips'):
            audio.tags['COMM'] = COMM(encoding=encoding, lang='eng', desc='Comment', text=metadata['tips'])
        
        audio.save()
        logger.info("WAV元数据添加成功")
        return True
        
    except Exception as e:
        logger.error(f"添加WAV元数据失败: {e}")
        logger.error(traceback.format_exc())
        return False

def add_metadata_to_aiff(file_path, metadata):
    """向AIFF文件添加元数据"""
    try:
        logger.info(f"开始处理AIFF文件: {file_path}")
        audio = AIFF(file_path)
        
        # AIFF文件通常使用ID3标签
        if not audio.tags:
            audio.add_tags()
        
        encoding = 3  # UTF-8编码
        
        # 设置基本元数据
        if metadata.get('title'):
            audio.tags['TIT2'] = TIT2(encoding=encoding, text=metadata['title'])
        if metadata.get('artist'):
            audio.tags['TPE1'] = TPE1(encoding=encoding, text=metadata['artist'])
        if metadata.get('album'):
            audio.tags['TALB'] = TALB(encoding=encoding, text=metadata['album'])
        if metadata.get('year'):
            audio.tags['TDRC'] = TDRC(encoding=encoding, text=str(metadata['year']))
        if metadata.get('lyrics'):
            audio.tags['USLT'] = USLT(encoding=encoding, lang='eng', desc='Lyrics', text=metadata['lyrics'])
        if metadata.get('tips'):
            audio.tags['COMM'] = COMM(encoding=encoding, lang='eng', desc='Comment', text=metadata['tips'])
        
        audio.save()
        logger.info("AIFF元数据添加成功")
        return True
        
    except Exception as e:
        logger.error(f"添加AIFF元数据失败: {e}")
        logger.error(traceback.format_exc())
        return False

def add_metadata_to_file(file_path, metadata):
    """根据文件类型添加元数据"""
    try:
        # 首先清理现有元数据
        strip_existing_metadata(file_path)
        
        # 检测文件类型
        file_ext = os.path.splitext(file_path)[1].lower()
        
        if file_ext == '.mp3':
            return add_metadata_to_mp3(file_path, metadata)
        elif file_ext == '.flac':
            return add_metadata_to_flac(file_path, metadata)
        elif file_ext in ['.ogg', '.oga']:
            return add_metadata_to_ogg(file_path, metadata)
        elif file_ext in ['.m4a', '.mp4']:
            return add_metadata_to_mp4(file_path, metadata)
        elif file_ext == '.wav':
            return add_metadata_to_wav(file_path, metadata)
        elif file_ext == '.aiff':
            return add_metadata_to_aiff(file_path, metadata)
        else:
            logger.error(f"不支持的文件格式: {file_ext}")
            return False
            
    except Exception as e:
        logger.error(f"处理文件时出错: {e}")
        logger.error(traceback.format_exc())
        return False

def cleanup_old_files():
    """清理旧文件"""
    while True:
        time.sleep(60)
        if is_shutting_down:
            break
            
        current_time = time.time()
        files_to_delete = []
        
        for file_id, file_info in list(file_registry.items()):
            if current_time - file_info['created_time'] > FILE_CLEANUP_TIME:
                files_to_delete.append((file_id, file_info['path']))
        
        for file_id, file_path in files_to_delete:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                del file_registry[file_id]
                logger.info(f"已清理文件: {file_path}")
            except Exception as e:
                logger.error(f"清理文件失败: {e}")

@app.route('/process-music', methods=['POST', 'OPTIONS'])
def process_music():
    """处理音乐文件"""
    if is_shutting_down:
        return jsonify({'error': '服务器正在关闭'}), 503
        
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'})
    
    try:
        # 安全解析JSON数据
        try:
            raw_data = request.get_data(as_text=True)
            data = safe_json_parse(raw_data)
        except Exception as e:
            logger.error(f"JSON解析失败: {e}")
            return jsonify({'error': '无效的JSON数据格式'}), 400
        
        logger.info(f"收到请求: {data.get('title', '未知标题')}")
        
        if not data:
            return jsonify({'error': '无效的JSON数据'}), 400
        
        # 验证必需参数
        required_fields = ['url', 'title']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'缺少必需字段: {field}'}), 400
        
        # 生成唯一文件ID
        file_id = str(uuid.uuid4())
        url_path = urlparse(data['url']).path
        original_filename = os.path.basename(url_path) or "audio.mp3"
        
        # 文件路径
        temp_file_path = os.path.join(TEMP_DIR, f"{file_id}_{original_filename}")
        processed_file_path = os.path.join(TEMP_DIR, f"processed_{file_id}_{original_filename}")
        
        # 下载原始文件（使用多线程优化）
        if not download_file(data['url'], temp_file_path):
            return jsonify({'error': '音乐文件下载失败'}), 500
        
        # 检查文件是否存在且大小合理
        if not os.path.exists(temp_file_path) or os.path.getsize(temp_file_path) == 0:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            return jsonify({'error': '下载的文件无效'}), 500
        
        # 并行下载封面和处理元数据
        cover_future = download_executor.submit(download_cover, data.get('cover_url'))
        
        # 等待封面下载完成
        cover_data = cover_future.result()
        
        # 准备元数据
        metadata = {
            'title': data['title'],
            'artist': data.get('artist', ''),
            'album': data.get('album', ''),
            'year': data.get('year', ''),
            'lyrics': data.get('lyrics', ''),
            'tips': data.get('tips', ''),
            'cover_data': cover_data
        }
        
        # 复制文件到新路径
        shutil.copy2(temp_file_path, processed_file_path)
        
        # 清理原始文件
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        
        # 使用线程池处理元数据
        metadata_future = metadata_executor.submit(add_metadata_to_file, processed_file_path, metadata)
        
        # 等待元数据处理完成
        if not metadata_future.result():
            if os.path.exists(processed_file_path):
                os.remove(processed_file_path)
            return jsonify({'error': '添加元数据失败，可能是不支持的文件格式'}), 500
        
        # 注册文件
        file_registry[file_id] = {
            'path': processed_file_path,
            'filename': original_filename,
            'created_time': time.time()
        }
        
        download_url = f"http://{request.host}/download/{file_id}"
        return jsonify({
            'success': True,
            'download_url': download_url,
            'file_id': file_id,
            'message': '文件处理成功'
        })
    
    except Exception as e:
        logger.error(f"处理请求时发生错误: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f'服务器内部错误: {str(e)}'}), 500

@app.route('/download/<file_id>')
def download_file_endpoint(file_id):
    """下载文件"""
    if is_shutting_down:
        return jsonify({'error': '服务器正在关闭'}), 503
        
    if file_id not in file_registry:
        return jsonify({'error': '文件不存在或已过期'}), 404
    
    file_info = file_registry[file_id]
    if not os.path.exists(file_info['path']):
        return jsonify({'error': '文件不存在'}), 404
    
    return send_file(
        file_info['path'],
        as_attachment=True,
        download_name=f"processed_{file_info['filename']}"
    )

@app.route('/shutdown', methods=['POST'])
def shutdown():
    """关闭服务器"""
    global is_shutting_down
    is_shutting_down = True
    
    # 关闭线程池
    download_executor.shutdown(wait=False)
    metadata_executor.shutdown(wait=False)
    
    # 关闭会话
    download_session.close()
    
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()
    return jsonify({'status': 'shutting_down', 'message': '服务器正在关闭'})

@app.route('/status')
def status():
    """返回服务器状态"""
    if is_shutting_down:
        return jsonify({'status': 'shutting_down'}), 503
    return jsonify({'status': 'success', 'message': '服务器运行正常'})

@app.route('/')
def index():
    return jsonify({
        'status': 'running',
        'endpoints': {
            'process_music': 'POST /process-music',
            'download': 'GET /download/<file_id>',
            'status': 'GET /status',
            'shutdown': 'POST /shutdown'
        }
    })

def init_app(cache_dir=None):
    """初始化应用程序"""
    global TEMP_DIR, logger
    
    # 设置缓存目录
    if cache_dir and os.path.exists(cache_dir):
        TEMP_DIR = cache_dir
        logger.info(f"使用自定义缓存目录: {TEMP_DIR}")
    else:
        TEMP_DIR = tempfile.gettempdir()
        logger.info(f"使用系统临时目录: {TEMP_DIR}")
    
    # 设置日志
    logging.basicConfig(
        level=logging.INFO, 
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(os.path.join(TEMP_DIR, 'music_metadata_processor.log'))
        ]
    )
    logger = logging.getLogger(__name__)
    
    # 启动清理线程
    cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
    cleanup_thread.start()
    
    logger.info("应用程序初始化完成")
    return app

def run_server(host='127.0.0.1', port=5000, cache_dir=None):
    """运行服务器"""
    init_app(cache_dir)
    logger.info(f"服务器启动: http://{host}:{port}")
    logger.info(f"临时目录: {TEMP_DIR}")
    app.run(host=host, port=port, debug=False, threaded=True)

if __name__ == '__main__':
    run_server()