# Google Detect Menu Projesi Dokümantasyonu

![Python](https://img.shields.io/badge/python-3.9%2B-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-00a393) ![Playwright](https://img.shields.io/badge/Playwright-1.58.0-2EAD33)

## Proje Özeti

**GoogleDetectMenu**, Google Maps URL'lerinden restoran veya mekanların "Menü" bilgilerini ve menü fotoğraflarını tespit edip çıkaran bir FastAPI tabanlı API sunucusu ve web scraping otomasyon aracıdır.
Özellikle güncel Google Maps arayüzüne (Haziran 2025 ve sonrası) uyumlu olacak şekilde, Playwright kullanarak dinamik içerikleri ve XHR/AJAX isteklerini yakalar.

Araç, tekli URL sorgulamasını ve bir Excel dosyası üzerinden toplu menü taramasını (Bulk Scrape) destekler.

## Amaç ve Hedefler

Bu projenin temel amacı, bir mekanın Google Maps linki verildiğinde:
1. **Adım 1.1 (Menü Linki Tespiti):** Sayfa üzerinde doğrudan bir "Menü" yönlendirme linki olup olmadığını bulmak.
2. **Adım 1.3 (Menü Fotoğraf Tarama):** Eğer link yoksa veya spesifik olarak görsellere ihtiyaç varsa, "Menü" sekmesine tıklayarak XHR (Ajax) isteklerini dinlemek ve paylaşılan menü fotoğraflarının kaynak URL'lerini (`lh3.googleusercontent.com`) yakalamak.
3. Yakalanan görselleri yerel diske (`images/` klasörüne) indirmek ve sonuçları temiz bir JSON formatında kullanıcıya sunmak.

## Özellikler

- 🌐 **Tekli ve Toplu Tarama**: Tek bir Google Maps URL'si veya binlerce satırlık bir Excel listesi üzerinden toplu işlem (Bulk) başlatabilme yeteneği.
- 📸 **Gelişmiş Fotoğraf Yakalama (XHR Intercept)**: Menü tabındaki fotoğrafların sayfaya yüklenirken arkada dönen JSON isteklerinden parse edilerek tarihlerine göre (Haziran 2025 ve sonrası) filtrelenmesi.
- 🚀 **Asenkron Mimari**: FastAPI ve Playwright'ın asenkron özellikleri sayesinde bloklanmayan, yüksek performanslı yapı.
- 🗂️ **Excel Dışa Aktarma**: Toplu işlemler sonucunda elde edilen verileri (mekan adı, menü linkleri, kaynak) anında Excel dosyası olarak indirebilme.
- 📊 **Görev Durumu ve Geçmiş**: Çalışan arka plan görevlerinin (job) durumunu anlık takip edebilme ve son 50 sorgunun geçmişini görebilme.

## Kullanılan Teknolojiler

- **Python 3**: Ana programlama dili.
- **FastAPI & Uvicorn**: Yüksek performanslı REST API sunucusu.
- **Playwright**: Headless/Headful tarayıcı otomasyonu (DOM manipülasyonu, XHR dinleme).
- **Pandas & openpyxl**: Excel (.xlsx) verilerinin okunması ve yazılması.
- **Aiohttp**: Fotoğrafların asenkron olarak indirilmesi.

## Kurulum Adımları

```bash
# 1. Sanal ortam (virtual environment) oluşturun ve aktifleştirin
python -m venv venv
source venv/bin/activate  # Windows için: venv\Scripts\activate

# 2. Bağımlılıkları yükleyin
pip install -r requirements.txt

# 3. Playwright Chromium tarayıcısını indirin
playwright install chromium
```

## Kullanım

Projeyi başlatmak için ana dizindeki `main.py` dosyasını çalıştırın:

```bash
python main.py
```

Uygulama varsayılan olarak `http://127.0.0.1:8001` (Windows) veya `http://0.0.0.0:8001` (Linux/Mac) adresinde ayağa kalkar.

### API Endpointleri (Swagger UI)

Tarayıcınızda `http://127.0.0.1:8001/docs` adresine giderek Swagger UI üzerinden tüm endpointleri görebilir ve test edebilirsiniz.

Temel Endpointler:
- `GET /health` : Sunucu ve Playwright profilinin durumunu kontrol eder.
- `POST /api/maps-menu` : Tek bir Google Maps URL'sini tarar ve menü sonuçlarını (varsa link, yoksa fotoğraf listesi) döner.
- `POST /api/maps-menu-bulk/start` : Excel dosyası yükleyerek toplu tarama işlemini başlatır. Excel dosyasında `url` isimli bir sütun bulunması zorunludur.
- `GET /api/maps-menu-bulk/status/{job_id}` : Toplu tarama işleminin yüzdelik durumunu, bitip bitmediğini ve (bittiyse) sonuçlarını döner.
- `GET /api/maps-menu-bulk/download/{job_id}?format=excel` : Toplu tarama sonuçlarını JSON veya Excel olarak indirir.
- `GET /api/history` : Uygulama üzerindeki geçmiş sorguları gösterir.

## Proje Mimarisi (Klasör Yapısı)

```text
googleDetectMenu/
├── config/                  # Yapılandırma ve sabit değişkenler
├── images/                  # İndirilen menü fotoğrafları buraya kaydedilir
├── logs/                    # Log kayıtları (INFO, DEBUG, vb.)
├── src/
│   ├── api/                 # FastAPI router'ları, state (job) yönetimi ve pydantic şemaları
│   │   ├── routes.py
│   │   ├── schemas.py
│   │   ├── server.py
│   │   └── state.py
│   ├── scraper/             # Web Scraping mantığı
│   │   ├── browser_config.py      # Playwright tarayıcı ayarları ve optimizasyon
│   │   ├── google_maps_scraper.py # Ana orkestrasyon, Maps açılışı ve mekan adını çekme
│   │   ├── menu_link_extractor.py # Adım 1.1: Menü URL linki tespiti
│   │   └── menu_photo_extract.py  # Adım 1.3: Fotoğraf sekmesine tıklama ve XHR verisi ayıklama
│   └── utils/
│       └── logger.py        # Gelişmiş günlük kaydı modülü
├── main.py                  # Uygulamayı başlatan giriş dosyası
├── requirements.txt         # Proje bağımlılıkları
└── menu_mobilenet_model.h5  # (Legacy/Harici Model) Görsel analizi için model dosyası
```

## Geliştirici Notları ve Uyarılar

- **Asenkron Döngüler:** Windows işletim sisteminde Playwright ile yaşanan Proactor event loop hatalarını önlemek için `main.py` içerisinde özel asenkron yapılandırma (`WindowsProactorEventLoopPolicy`) kullanılmaktadır.
- **Tarih Kriteri:** Fotoğraf aramalarında eski menüleri saf dışı bırakmak için `src/scraper/menu_photo_extract.py` içerisinde `_MIN_MENU_DATE` sabiti tanımlanmıştır (Minimum Haziran 2025). Gerekirse değiştirilebilir.
- **Klasör İzinleri:** İndirilen fotoğrafların ve kaydedilen logların sağlıklı yazılabilmesi için uygulamanın çalıştığı dizinde yazma yetkisi bulunmalıdır.
