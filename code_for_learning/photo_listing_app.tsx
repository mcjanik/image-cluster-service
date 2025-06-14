import React, { useState, useRef } from 'react';
import { Upload, Camera, Image, Save, X, Plus, Trash2, Clock, Star, Crown, Eye, Menu, ArrowLeft } from 'lucide-react';

const PhotoListingApp = () => {
  const [currentStep, setCurrentStep] = useState('upload'); // 'upload', 'results', 'promotion'
  const [uploadedImages, setUploadedImages] = useState([]);
  const [processing, setProcessing] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [results, setResults] = useState([]);
  const [publishedItems, setPublishedItems] = useState([]);
  const [userDescription, setUserDescription] = useState('');
  const fileInputRef = useRef(null);

  // Категории классифайдов как на Somon.tj
  const categories = {
    'Недвижимость': ['Квартиры', 'Дома', 'Дачи', 'Коммерческая недвижимость', 'Земельные участки', 'Гаражи'],
    'Транспорт': ['Легковые автомобили', 'Грузовики', 'Мотоциклы', 'Автозапчасти', 'Шины и диски'],
    'Электроника и бытовая техника': ['Телефоны и связь', 'Компьютеры и оргтехника', 'Телевизоры', 'Аудиотехника', 'Фото и видео'],
    'Одежда и личные вещи': ['Мужская одежда', 'Женская одежда', 'Детская одежда', 'Обувь', 'Аксессуары'],
    'Все для дома': ['Мебель', 'Бытовая техника', 'Посуда', 'Текстиль', 'Инструменты'],
    'Детский мир': ['Детская одежда', 'Детская обувь', 'Детская мебель', 'Детские автокресла', 'Детские коляски', 'Игрушки'],
    'Строительство, сырье и ремонт': ['Стройматериалы', 'Инструменты', 'Сантехника', 'Электрика'],
    'Работа': ['Вакансии', 'Резюме', 'Услуги']
  };

  const conditions = ['Новое', 'Отличное', 'Хорошее', 'Удовлетворительное', 'На запчасти'];
  const currencies = ['сомони', 'доллар', 'евро'];

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    const files = Array.from(e.dataTransfer.files);
    handleFiles(files);
  };

  const handleFileSelect = (e) => {
    const files = Array.from(e.target.files);
    handleFiles(files);
  };

  const handleFiles = (files) => {
    const imageFiles = files.filter(file => file.type.startsWith('image/'));

    imageFiles.forEach(file => {
      const reader = new FileReader();
      reader.onload = (e) => {
        setUploadedImages(prev => [...prev, {
          id: Date.now() + Math.random(),
          file,
          preview: e.target.result,
          name: file.name
        }]);
      };
      reader.readAsDataURL(file);
    });
  };

  const removeImage = (id) => {
    setUploadedImages(prev => prev.filter(img => img.id !== id));
  };

  const processImages = async () => {
    setProcessing(true);

    // Симуляция обработки (здесь будет API вызов с фото + userDescription)
    await new Promise(resolve => setTimeout(resolve, 3000));

    // Создаем результаты на основе загруженных фотографий (правильная привязка)
    // В реальном приложении сюда придут данные из LLM API, который обработает фото + текст
    const mockResults = uploadedImages.map((img, index) => {
      const categories_templates = [
        { main: 'Одежда и личные вещи', sub: 'Обувь', title: 'Стильные кроссовки', desc: 'Удобные кроссовки в отличном состоянии. Размер указан на фото.', price: '250', brand: 'Nike' },
        { main: 'Детский мир', sub: 'Детские автокресла', title: 'Детское автокресло', desc: 'Безопасное автокресло для детей. Поворотное, с 5-точечными ремнями.', price: '800', brand: 'MAXI-COSI' },
        { main: 'Электроника и бытовая техника', sub: 'Компьютеры и оргтехника', title: 'Ноутбук для работы', desc: 'Производительный ноутбук. Подходит для работы и учебы.', price: '1500', brand: 'HP' },
        { main: 'Все для дома', sub: 'Бытовая техника', title: 'Бытовая техника', desc: 'Качественная техника для дома в хорошем состоянии.', price: '400', brand: 'Samsung' },
        { main: 'Транспорт', sub: 'Автозапчасти', title: 'Автозапчасти', desc: 'Оригинальные запчасти в отличном состоянии.', price: '150', brand: 'Original' }
      ];

      const template = categories_templates[index % categories_templates.length];

      // В реальном приложении здесь LLM учтет userDescription и создаст более точное описание
      let enhancedDescription = template.desc;
      if (userDescription) {
        enhancedDescription += ' ' + 'Дополнительные детали указаны владельцем.';
      }

      return {
        id: img.id, // Используем ID изображения для правильной привязки
        images: [img.preview], // Правильно привязываем конкретное фото
        mainCategory: template.main,
        subCategory: template.sub,
        title: template.title,
        description: enhancedDescription,
        price: template.price,
        currency: 'сомони',
        brand: template.brand,
        condition: 'Отличное',
        location: 'Душанбе',
        userInput: userDescription // Сохраняем пользовательский ввод для API
      };
    });

    setResults(mockResults);
    setProcessing(false);
    setCurrentStep('results');
  };

  const updateResult = (id, field, value) => {
    setResults(prev => prev.map(item =>
      item.id === id ? { ...item, [field]: value } : item
    ));
  };

  const deleteResult = (id) => {
    setResults(prev => prev.filter(item => item.id !== id));
  };

  const publishItem = (item) => {
    setPublishedItems(prev => [...prev, { ...item, promotionType: 'standard', days: 0 }]);
  };

  const publishAllItems = () => {
    const itemsToPublish = results.map(item => ({ ...item, promotionType: 'standard', days: 0 }));
    setPublishedItems(itemsToPublish);
    setCurrentStep('promotion');
  };

  const updatePromotion = (id, promotionType, days) => {
    setPublishedItems(prev => prev.map(item =>
      item.id === id ? { ...item, promotionType, days } : item
    ));
  };

  // Подсчет статистики
  const getPromotionStats = () => {
    const stats = {
      standard: publishedItems.filter(item => item.promotionType === 'standard').length,
      top: publishedItems.filter(item => item.promotionType === 'top').length,
      vip: publishedItems.filter(item => item.promotionType === 'vip').length,
      total: 0
    };

    stats.total = publishedItems.reduce((sum, item) => {
      if (item.promotionType === 'top') return sum + (5 * item.days);
      if (item.promotionType === 'vip') return sum + (10 * item.days);
      return sum;
    }, 0);

    return stats;
  };

  // Логотип Somon.tj
  const SomonLogo = () => (
    <div className="flex items-center">
      <span className="text-blue-600 font-bold text-xl">So</span>
      <span className="text-orange-500 font-bold text-xl">mon</span>
      <span className="text-green-500 font-bold text-xl">.tj</span>
    </div>
  );

  if (currentStep === 'upload') {
    return (
      <div className="min-h-screen bg-gray-50">
        {/* Mobile Header */}
        <div className="bg-white border-b border-gray-200 p-4">
          <div className="flex items-center justify-between">
            <SomonLogo />
            <Menu className="w-6 h-6 text-gray-600" />
          </div>
        </div>

        <div className="p-4">
          {/* Header */}
          <div className="text-center mb-6">
            <div className="inline-flex items-center justify-center w-16 h-16 bg-orange-500 rounded-full mb-4">
              <Camera className="w-8 h-8 text-white" />
            </div>
            <h1 className="text-2xl font-bold text-gray-800 mb-2">
              Подать объявление
            </h1>
            <p className="text-gray-600 text-sm">
              Загрузите фото товаров для автоматического создания объявлений
            </p>
          </div>

          {/* Upload Area */}
          <div className="bg-white rounded-lg border p-4 mb-6">
            <div
              className={`relative border-2 border-dashed rounded-lg p-6 transition-all ${dragActive
                  ? 'border-orange-500 bg-orange-50'
                  : 'border-gray-300'
                }`}
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
            >
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept="image/*"
                onChange={handleFileSelect}
                className="hidden"
              />

              <div className="text-center">
                <Upload className="w-10 h-10 text-gray-400 mx-auto mb-3" />
                <h3 className="text-base font-medium text-gray-700 mb-2">
                  Добавьте фотографии
                </h3>
                <p className="text-gray-500 text-sm mb-4">
                  Нажмите для выбора или перетащите сюда
                </p>
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="bg-orange-500 text-white px-6 py-2 rounded-lg text-sm font-medium"
                >
                  Выбрать фото
                </button>
              </div>
            </div>

            {/* Uploaded Images */}
            {uploadedImages.length > 0 && (
              <div className="mt-4">
                <h3 className="text-sm font-medium text-gray-700 mb-3">
                  Загружено: {uploadedImages.length} фото
                </h3>
                <div className="grid grid-cols-3 gap-2">
                  {uploadedImages.map((image) => (
                    <div key={image.id} className="relative">
                      <img
                        src={image.preview}
                        alt={image.name}
                        className="w-full h-24 object-cover rounded border"
                      />
                      <button
                        onClick={() => removeImage(image.id)}
                        className="absolute -top-1 -right-1 bg-red-500 text-white rounded-full w-5 h-5 flex items-center justify-center text-xs"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* User Description */}
            {uploadedImages.length > 0 && (
              <div className="mt-4">
                <h3 className="text-sm font-medium text-gray-700 mb-2">
                  Дополнительная информация о товарах
                </h3>
                <textarea
                  value={userDescription}
                  onChange={(e) => setUserDescription(e.target.value)}
                  placeholder="Например:
1. Кроссовки Nike, размер 42, новые, цена 500 сомони
2. Стиральная машина LG, 5кг, отличное состояние, 800 сомони  
3. Детское автокресло, красное, хорошее состояние, 300 сомони
4. Монитор HP 24 дюйма, отличное состояние, 400 сомони

Укажите названия, размеры, цены, состояние - это поможет создать более точные объявления."
                  rows={6}
                  className="w-full p-3 border border-gray-300 rounded-lg text-sm placeholder-gray-400 focus:ring-1 focus:ring-orange-500 focus:border-orange-500"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Необязательно • Поможет создать более точные описания
                </p>
              </div>
            )}

            {/* Process Button */}
            {uploadedImages.length > 0 && (
              <div className="mt-4">
                <button
                  onClick={processImages}
                  disabled={processing}
                  className="w-full bg-orange-500 text-white py-3 rounded-lg font-medium disabled:opacity-50"
                >
                  {processing ? (
                    <div className="flex items-center justify-center">
                      <Clock className="w-4 h-4 mr-2 animate-spin" />
                      Обрабатываем...
                    </div>
                  ) : (
                    'Создать объявления'
                  )}
                </button>
              </div>
            )}
          </div>

          {/* Features */}
          <div className="space-y-3">
            <div className="bg-white rounded-lg border p-4 flex items-center">
              <Image className="w-8 h-8 text-orange-500 mr-3 flex-shrink-0" />
              <div>
                <h3 className="font-medium text-gray-800 text-sm">Распознавание товаров</h3>
                <p className="text-gray-600 text-xs">Автоматически определяем что на фото</p>
              </div>
            </div>

            <div className="bg-white rounded-lg border p-4 flex items-center">
              <Save className="w-8 h-8 text-orange-500 mr-3 flex-shrink-0" />
              <div>
                <h3 className="font-medium text-gray-800 text-sm">Умные описания</h3>
                <p className="text-gray-600 text-xs">Создаем подробные описания + ваши данные</p>
              </div>
            </div>

            <div className="bg-white rounded-lg border p-4 flex items-center">
              <Plus className="w-8 h-8 text-orange-500 mr-3 flex-shrink-0" />
              <div>
                <h3 className="font-medium text-gray-800 text-sm">Легкое редактирование</h3>
                <p className="text-gray-600 text-xs">Изменяйте перед публикацией</p>
              </div>
            </div>

            {userDescription && (
              <div className="bg-orange-50 border border-orange-200 rounded-lg p-4 flex items-center">
                <div className="w-2 h-2 bg-orange-500 rounded-full mr-3 flex-shrink-0"></div>
                <div>
                  <h3 className="font-medium text-orange-800 text-sm">Дополнительная информация добавлена</h3>
                  <p className="text-orange-600 text-xs">Это поможет создать более точные объявления</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  if (currentStep === 'promotion') {
    const stats = getPromotionStats();

    return (
      <div className="min-h-screen bg-gray-50">
        {/* Mobile Header */}
        <div className="bg-white border-b border-gray-200 p-4">
          <div className="flex items-center">
            <button onClick={() => setCurrentStep('results')} className="mr-3">
              <ArrowLeft className="w-6 h-6 text-gray-600" />
            </button>
            <div className="flex-1">
              <h1 className="text-lg font-bold text-gray-800">Продвижение</h1>
            </div>
          </div>
        </div>

        <div className="p-4">
          <div className="bg-white rounded-lg border p-4 mb-4">
            <h2 className="text-base font-medium text-gray-800 mb-3">Продвижение объявлений</h2>
            <p className="text-sm text-gray-600 mb-4">
              Увеличьте просмотры с помощью ТОП и ВИП размещения
            </p>
          </div>

          <div className="space-y-4 mb-6">
            {publishedItems.map((item) => (
              <PromotionCard key={item.id} item={item} onUpdate={updatePromotion} />
            ))}
          </div>

          {/* Статистика */}
          <div className="bg-white rounded-lg border p-4 mb-6">
            <h3 className="font-medium text-gray-800 mb-3">Итого</h3>
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">Обычных объявлений:</span>
                <span className="font-medium">{stats.standard}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">ТОП объявлений:</span>
                <span className="font-medium text-yellow-600">{stats.top}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">ВИП объявлений:</span>
                <span className="font-medium text-purple-600">{stats.vip}</span>
              </div>
              <div className="border-t pt-2">
                <div className="flex justify-between">
                  <span className="font-medium text-gray-800">Общая стоимость:</span>
                  <span className="font-bold text-orange-500">{stats.total} сомони</span>
                </div>
              </div>
            </div>
          </div>

          <button
            onClick={() => alert('Объявления опубликованы!')}
            className="w-full bg-orange-500 text-white py-3 rounded-lg font-medium"
          >
            Опубликовать за {stats.total} сомони
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Mobile Header */}
      <div className="bg-white border-b border-gray-200 p-4">
        <div className="flex items-center">
          <button onClick={() => setCurrentStep('upload')} className="mr-3">
            <ArrowLeft className="w-6 h-6 text-gray-600" />
          </button>
          <div className="flex-1">
            <h1 className="text-lg font-bold text-gray-800">Проверьте объявления</h1>
            <p className="text-xs text-gray-600">Найдено {results.length} товаров</p>
          </div>
        </div>
      </div>

      <div className="p-4">
        {/* Results */}
        <div className="space-y-4 mb-6">
          {results.map((item) => (
            <ResultCard
              key={item.id}
              item={item}
              categories={categories}
              conditions={conditions}
              currencies={currencies}
              onUpdate={updateResult}
              onDelete={deleteResult}
              onPublish={publishItem}
            />
          ))}
        </div>

        {/* Actions */}
        {results.length > 0 && (
          <button
            onClick={publishAllItems}
            className="w-full bg-orange-500 text-white py-3 rounded-lg font-medium"
          >
            Опубликовать все ({results.length})
          </button>
        )}
      </div>
    </div>
  );
};

const ResultCard = ({ item, categories, conditions, currencies, onUpdate, onDelete, onPublish }) => {
  const [formData, setFormData] = useState(item);
  const [isExpanded, setIsExpanded] = useState(false);

  const handleChange = (field, value) => {
    const newData = { ...formData, [field]: value };
    setFormData(newData);
    onUpdate(item.id, field, value);
  };

  const handleMainCategoryChange = (mainCategory) => {
    handleChange('mainCategory', mainCategory);
    if (categories[mainCategory] && categories[mainCategory].length > 0) {
      handleChange('subCategory', categories[mainCategory][0]);
    }
  };

  return (
    <div className="bg-white rounded-lg border">
      {/* Card Header */}
      <div className="p-4">
        <div className="flex">
          <img
            src={item.images[0]}
            alt={formData.title}
            className="w-16 h-16 object-cover rounded mr-3 flex-shrink-0"
          />
          <div className="flex-1 min-w-0">
            <input
              type="text"
              value={formData.title}
              onChange={(e) => handleChange('title', e.target.value)}
              className="w-full font-medium text-gray-800 border-none p-0 text-sm bg-transparent"
              placeholder="Название товара"
            />
            <div className="flex items-center mt-1">
              <input
                type="number"
                value={formData.price}
                onChange={(e) => handleChange('price', e.target.value)}
                className="w-16 text-orange-500 font-bold text-sm border-none p-0 bg-transparent"
                placeholder="0"
              />
              <span className="text-orange-500 font-bold text-sm ml-1">{formData.currency}</span>
            </div>
            <div className="flex items-center mt-1">
              <span className="bg-orange-100 text-orange-800 px-2 py-0.5 rounded text-xs">
                {formData.mainCategory}
              </span>
            </div>
          </div>
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-gray-400 p-1"
          >
            {isExpanded ? <X className="w-5 h-5" /> : <Plus className="w-5 h-5" />}
          </button>
        </div>
      </div>

      {/* Expanded Content */}
      {isExpanded && (
        <div className="px-4 pb-4 border-t border-gray-100 pt-4 space-y-3">
          {/* Categories */}
          <div>
            <label className="block text-xs text-gray-600 mb-1">Категория</label>
            <select
              value={formData.mainCategory}
              onChange={(e) => handleMainCategoryChange(e.target.value)}
              className="w-full p-2 border border-gray-300 rounded text-sm"
            >
              {Object.keys(categories).map(cat => (
                <option key={cat} value={cat}>{cat}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs text-gray-600 mb-1">Подкатегория</label>
            <select
              value={formData.subCategory}
              onChange={(e) => handleChange('subCategory', e.target.value)}
              className="w-full p-2 border border-gray-300 rounded text-sm"
            >
              {categories[formData.mainCategory]?.map(subcat => (
                <option key={subcat} value={subcat}>{subcat}</option>
              ))}
            </select>
          </div>

          {/* Description */}
          <div>
            <label className="block text-xs text-gray-600 mb-1">Описание</label>
            <textarea
              value={formData.description}
              onChange={(e) => handleChange('description', e.target.value)}
              rows={3}
              className="w-full p-2 border border-gray-300 rounded text-sm"
              placeholder="Описание товара"
            />
          </div>

          {/* Additional Fields */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-600 mb-1">Бренд</label>
              <input
                type="text"
                value={formData.brand}
                onChange={(e) => handleChange('brand', e.target.value)}
                className="w-full p-2 border border-gray-300 rounded text-sm"
                placeholder="Бренд"
              />
            </div>

            <div>
              <label className="block text-xs text-gray-600 mb-1">Состояние</label>
              <select
                value={formData.condition}
                onChange={(e) => handleChange('condition', e.target.value)}
                className="w-full p-2 border border-gray-300 rounded text-sm"
              >
                {conditions.map(cond => (
                  <option key={cond} value={cond}>{cond}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs text-gray-600 mb-1">Местоположение</label>
            <input
              type="text"
              value={formData.location}
              onChange={(e) => handleChange('location', e.target.value)}
              className="w-full p-2 border border-gray-300 rounded text-sm"
              placeholder="Город"
            />
          </div>

          {/* Actions */}
          <div className="flex space-x-2 pt-2">
            <button
              onClick={() => onDelete(item.id)}
              className="flex-1 bg-red-50 text-red-600 py-2 rounded text-sm font-medium"
            >
              Удалить
            </button>
            <button
              onClick={() => onPublish(formData)}
              className="flex-1 bg-orange-500 text-white py-2 rounded text-sm font-medium"
            >
              Опубликовать
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

const PromotionCard = ({ item, onUpdate }) => {
  const [promotionType, setPromotionType] = useState('standard');
  const [days, setDays] = useState(3);

  const handlePromotionChange = (type, dayCount) => {
    setPromotionType(type);
    setDays(dayCount);
    onUpdate(item.id, type, dayCount);
  };

  const promotionOptions = [
    { type: 'standard', name: 'Обычное', price: 0, icon: Eye, desc: 'Стандартное размещение' },
    { type: 'top', name: 'ТОП', price: 5, icon: Star, desc: 'Показ в топе категории' },
    { type: 'vip', name: 'ВИП', price: 10, icon: Crown, desc: 'Приоритетный показ' }
  ];

  return (
    <div className="bg-white rounded-lg border p-4">
      <div className="flex mb-4">
        <img src={item.images[0]} alt={item.title} className="w-12 h-12 object-cover rounded mr-3" />
        <div className="flex-1">
          <h3 className="font-medium text-gray-800 text-sm">{item.title}</h3>
          <p className="text-xs text-gray-600">{item.price} {item.currency}</p>
        </div>
      </div>

      <div className="space-y-3">
        {promotionOptions.map((option) => {
          const IconComponent = option.icon;
          const isSelected = promotionType === option.type;

          return (
            <div
              key={option.type}
              className={`border rounded-lg p-3 cursor-pointer transition-all ${isSelected
                  ? 'border-orange-500 bg-orange-50'
                  : 'border-gray-200'
                }`}
              onClick={() => handlePromotionChange(option.type, option.type === 'standard' ? 0 : days)}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center">
                  <IconComponent className={`w-4 h-4 mr-2 ${option.type === 'standard' ? 'text-gray-500' :
                      option.type === 'top' ? 'text-yellow-500' :
                        'text-purple-500'
                    }`} />
                  <div>
                    <span className="font-medium text-sm">{option.name}</span>
                    <p className="text-xs text-gray-600">{option.desc}</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-sm font-medium">
                    {option.price === 0 ? 'Бесплатно' : `${option.price} с/день`}
                  </p>
                </div>
              </div>

              {isSelected && option.type !== 'standard' && (
                <div className="mt-2">
                  <select
                    value={days}
                    onChange={(e) => setDays(parseInt(e.target.value))}
                    className="w-full p-1 border border-gray-300 rounded text-sm"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <option value={3}>3 дня</option>
                    <option value={7}>7 дней</option>
                    <option value={14}>14 дней</option>
                    <option value={30}>30 дней</option>
                  </select>
                  <p className="text-xs text-orange-600 mt-1">
                    Итого: {option.price * days} сомони
                  </p>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default PhotoListingApp;