SET NAMES utf8mb4;
SET collation_connection = 'utf8mb4_unicode_ci';

INSERT INTO product_types (id, type_name) VALUES
    (1, 'Вклад'),
    (2, 'Счет'),
    (3, 'ИИС'),
    (4, 'Карта')
ON DUPLICATE KEY UPDATE type_name = VALUES(type_name);

INSERT INTO risk_level (id, category) VALUES
    (1, 'Низкий'),
    (2, 'Средний'),
    (3, 'Высокий')
ON DUPLICATE KEY UPDATE category = VALUES(category);

INSERT INTO tbl_currencies (id, currency_code) VALUES
    (1, 'CNY'),
    (2, 'RUB'),
    (3, 'USD'),
    (4, 'EUR')
ON DUPLICATE KEY UPDATE currency_code = VALUES(currency_code);

INSERT INTO banks (id, bank_name, license_no, rating) VALUES
    (1, 'СберБанк', '1481', 'AAA'),
    (2, 'ВТБ', '1000', 'AAA'),
    (3, 'Альфа-Банк', '1326', 'AA+'),
    (4, 'Т-Банк', '2673', 'A+'),
    (5, 'Газпромбанк', '354', 'AA'),
    (6, 'ПСБ', '3251', 'AA+'),
    (7, 'Россельхозбанк', '3349', 'AA-'),
    (8, 'Совкомбанк', '963', 'A+'),
    (9, 'МТС Банк', '2268', 'A'),
    (10, 'Открытие', '2209', 'A')
ON DUPLICATE KEY UPDATE
    bank_name = VALUES(bank_name),
    license_no = VALUES(license_no),
    rating = VALUES(rating);

INSERT INTO clients (id, full_name, passport, phone) VALUES
    (1, 'Иванов Иван Сергеевич', '4010 100001', '+79000000001'),
    (2, 'Петров Петр Алексеевич', '4010 100002', '+79000000002'),
    (3, 'Смирнов Алексей Олегович', '4010 100003', '+79000000003'),
    (4, 'Кузнецова Мария Игоревна', '4010 100004', '+79000000004'),
    (5, 'Попов Дмитрий Романович', '4010 100005', '+79000000005')
ON DUPLICATE KEY UPDATE
    full_name = VALUES(full_name),
    passport = VALUES(passport),
    phone = VALUES(phone);

INSERT INTO products (
    bank_id, type_id, risk_id, currency_id, client_id,
    product_title, interest_rate, min_deposit, term_months, description, is_active
) VALUES
    (1, 1, 1, 2, 1, 'Вклад Сбер Старт', 12.50, 10000, 12, 'Базовый вклад', TRUE),
    (1, 2, 1, 2, NULL, 'Счет Сбер Ежедневный', 8.20, 0, 0, 'Накопительный счет', TRUE),
    (1, 3, 2, 2, NULL, 'ИИС Сбер Инвест', 13.10, 50000, 36, 'Инвестиционный счет', TRUE),

    (2, 1, 1, 2, 2, 'Вклад ВТБ Доход', 12.90, 15000, 12, 'Классический вклад', TRUE),
    (2, 2, 1, 3, NULL, 'Счет ВТБ Валютный', 4.20, 100, 0, 'Валютный счет', TRUE),
    (2, 4, 2, 2, NULL, 'Карта ВТБ Процент', 1.90, 0, 0, 'Карта с процентом на остаток', TRUE),

    (3, 1, 1, 2, 3, 'Вклад Альфа Плюс', 13.40, 10000, 18, 'Повышенная ставка', TRUE),
    (3, 2, 1, 4, NULL, 'Счет Альфа EUR', 3.80, 100, 0, 'Счет в евро', TRUE),

    (4, 1, 1, 2, NULL, 'Вклад Т-Банк Максимум', 14.20, 50000, 12, 'Максимальная доходность', TRUE),
    (4, 3, 3, 2, NULL, 'ИИС Т-Банк Агрессивный', 15.10, 100000, 36, 'Повышенный риск', TRUE),

    (5, 1, 1, 1, NULL, 'Вклад Газпром CNY', 9.10, 10000, 12, 'Вклад в юанях', TRUE),
    (5, 2, 1, 2, 4, 'Счет Газпром Свободный', 8.70, 0, 0, 'Свободное пополнение', TRUE),

    (6, 1, 1, 2, NULL, 'Вклад ПСБ Надежный', 12.30, 30000, 12, 'Надежный вклад', TRUE),
    (7, 1, 1, 2, NULL, 'Вклад РСХБ Классика', 12.10, 10000, 24, 'Долгий срок', TRUE),
    (8, 2, 1, 2, 5, 'Счет Совком Базовый', 7.90, 0, 0, 'Накопительный продукт', TRUE),
    (9, 4, 2, 2, NULL, 'Карта МТС Доходная', 2.10, 0, 0, 'Карта для повседневных трат', TRUE),
    (10, 1, 1, 4, NULL, 'Вклад Открытие EUR', 4.10, 500, 12, 'Вклад в евро', TRUE)
ON DUPLICATE KEY UPDATE
    interest_rate = VALUES(interest_rate),
    min_deposit = VALUES(min_deposit),
    term_months = VALUES(term_months),
    description = VALUES(description),
    is_active = VALUES(is_active);
