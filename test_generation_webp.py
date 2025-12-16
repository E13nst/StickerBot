"""Тестовый скрипт для генерации изображения и конвертации в WebP"""
import asyncio
import io
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent))

from src.managers.wavespeed_client import WaveSpeedClient
from src.utils.image_postprocess import convert_to_webp_rgba, validate_alpha_channel
from src.config.settings import WAVESPEED_API_KEY, WAVESPEED_BG_REMOVE_ENABLED

load_dotenv()


async def test_generation_and_webp_conversion():
    """Генерирует изображение и конвертирует в WebP"""
    if not WAVESPEED_API_KEY:
        print("❌ WAVESPEED_API_KEY не установлен в .env")
        return
    
    prompt = "Trump with cigar"
    print(f"[GENERATION] Generating image: '{prompt}'...")
    
    client = WaveSpeedClient(WAVESPEED_API_KEY)
    
    try:
        # Шаг 1: Генерация через flux-schnell
        print("\n[1/6] Submitting generation request...")
        flux_request_id = await client.submit_flux_schnell(
            prompt,
            seed=-1,
            output_format="png"
        )
        print(f"   [OK] Request ID: {flux_request_id}")
        
        # Шаг 2: Polling результата flux
        print("\n[2/6] Waiting for generation result...")
        import time
        max_wait = 60  # максимум 60 секунд
        start_time = time.time()
        flux_image_url = None
        
        while time.time() - start_time < max_wait:
            await asyncio.sleep(2)
            result = await client.get_prediction_result(flux_request_id)
            
            if not result:
                continue
            
            # Проверяем структуру ответа
            if "data" in result and isinstance(result.get("data"), dict):
                data = result["data"]
                status = data.get("status", "").lower()
                outputs = data.get("outputs", [])
            else:
                status = result.get("status", "").lower()
                outputs = result.get("outputs", [])
            
            if status == "completed":
                if outputs:
                    flux_image_url = outputs[0]
                    print(f"   [OK] Image ready: {flux_image_url[:80]}...")
                    break
            elif status == "failed":
                error_msg = result.get("error") or (data.get("error") if "data" in result else "Unknown")
                print(f"   [ERROR] Generation failed: {error_msg}")
                return
        
        if not flux_image_url:
            print("   [ERROR] Generation timeout")
            return
        
        # Шаг 3: Background removal (если включено)
        final_image_url = flux_image_url
        if WAVESPEED_BG_REMOVE_ENABLED:
            print("\n[3/6] Removing background...")
            bg_request_id = await client.submit_background_remover(flux_image_url)
            print(f"   [OK] Request ID: {bg_request_id}")
            
            start_time = time.time()
            while time.time() - start_time < max_wait:
                await asyncio.sleep(2)
                result = await client.get_prediction_result(bg_request_id)
                
                if not result:
                    continue
                
                if "data" in result and isinstance(result.get("data"), dict):
                    data = result["data"]
                    status = data.get("status", "").lower()
                    outputs = data.get("outputs", [])
                else:
                    status = result.get("status", "").lower()
                    outputs = result.get("outputs", [])
                
                if status == "completed":
                    if outputs:
                        final_image_url = outputs[0]
                        print(f"   [OK] Background removed: {final_image_url[:80]}...")
                        break
                elif status == "failed":
                    print("   [WARN] Background removal failed, using original image")
                    break
        
        # Шаг 4: Скачивание изображения
        print("\n[4/6] Downloading image...")
        image_bytes = await client.download_image(final_image_url)
        if not image_bytes:
            print("   [ERROR] Failed to download image")
            return
        
        print(f"   [OK] Downloaded: {len(image_bytes)} bytes")
        
        # Шаг 5: Проверка альфа-канала
        print("\n[5/6] Checking alpha channel...")
        has_alpha = validate_alpha_channel(image_bytes)
        print(f"   [{'OK' if has_alpha else 'WARN'}] Alpha channel: {'present' if has_alpha else 'missing'}")
        
        # Шаг 6: Конвертация в WebP
        print("\n[6/6] Converting to WebP...")
        webp_bytes = convert_to_webp_rgba(image_bytes)
        print(f"   [OK] WebP created: {len(webp_bytes)} bytes")
        
        # Шаг 7: Сохранение результата
        output_dir = Path("test_output")
        output_dir.mkdir(exist_ok=True)
        
        # Сохраняем оригинал PNG
        png_path = output_dir / "trump_cigar_original.png"
        with open(png_path, "wb") as f:
            f.write(image_bytes)
        print(f"\n[SAVE] Original saved: {png_path}")
        
        # Сохраняем WebP
        webp_path = output_dir / "trump_cigar.webp"
        with open(webp_path, "wb") as f:
            f.write(webp_bytes)
        print(f"[SAVE] WebP saved: {webp_path}")
        
        # Показываем информацию о WebP
        from PIL import Image
        webp_img = Image.open(io.BytesIO(webp_bytes))
        print(f"\n[INFO] WebP details:")
        print(f"   Size: {webp_img.size[0]}x{webp_img.size[1]} px")
        print(f"   Mode: {webp_img.mode}")
        print(f"   File size: {len(webp_bytes)} bytes ({len(webp_bytes)/1024:.1f} KB)")
        
        print(f"\n[SUCCESS] Done! Open file: {webp_path.absolute()}")
        
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(test_generation_and_webp_conversion())

