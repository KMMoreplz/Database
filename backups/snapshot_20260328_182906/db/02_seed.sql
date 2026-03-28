INSERT INTO product_types (id, type_name) VALUES
    (1, 'Вклад'),
    (2, 'Счет'),
    (3, 'ИИС'),
    (4, 'Карта')
ON CONFLICT (id) DO NOTHING;

INSERT INTO risk_level (id, category) VALUES
    (1, 'Низкий'),
    (2, 'Средний'),
    (3, 'Высокий')
ON CONFLICT (id) DO NOTHING;

INSERT INTO tbl_currencies (id, currency_code) VALUES
    (1, 'CNY'),
    (2, 'RUB'),
    (3, 'USD'),
    (4, 'EUR')
ON CONFLICT (id) DO NOTHING;

INSERT INTO banks (bank_name, license_no, rating) VALUES
    ('СберБанк', '1481', 'AAA'),
    ('ВТБ', '1000', 'AAA'),
    ('Альфа-Банк', '1326', 'AA+'),
    ('Т-Банк', '2673', 'A+'),
    ('Газпромбанк', '354', 'AA'),
    ('ПСБ', '3251', 'AA+'),
    ('Россельхозбанк', '3349', 'AA-'),
    ('Совкомбанк', '963', 'A+'),
    ('МТС Банк', '2268', 'A'),
    ('Открытие', '2209', 'A')
ON CONFLICT (bank_name) DO NOTHING;

INSERT INTO clients (full_name, passport, phone) VALUES
    ('Иванов Иван Сергеевич', '4010 100001', '+79000000001'),
    ('Петров Петр Алексеевич', '4010 100002', '+79000000002'),
    ('Смирнов Алексей Олегович', '4010 100003', '+79000000003'),
    ('Кузнецова Мария Игоревна', '4010 100004', '+79000000004'),
    ('Попов Дмитрий Романович', '4010 100005', '+79000000005'),
    ('Васильева Анна Павловна', '4010 100006', '+79000000006'),
    ('Соколов Максим Денисович', '4010 100007', '+79000000007'),
    ('Морозова Елена Викторовна', '4010 100008', '+79000000008'),
    ('Новиков Кирилл Андреевич', '4010 100009', '+79000000009'),
    ('Федорова Ольга Михайловна', '4010 100010', '+79000000010'),
    ('Волков Артем Сергеевич', '4010 100011', '+79000000011'),
    ('Алексеев Николай Ильич', '4010 100012', '+79000000012'),
    ('Лебедева Ирина Андреевна', '4010 100013', '+79000000013'),
    ('Семенов Андрей Павлович', '4010 100014', '+79000000014'),
    ('Егоров Степан Романович', '4010 100015', '+79000000015'),
    ('Павлова Екатерина Олеговна', '4010 100016', '+79000000016'),
    ('Козлов Владислав Игоревич', '4010 100017', '+79000000017'),
    ('Николаева Юлия Михайловна', '4010 100018', '+79000000018'),
    ('Зайцев Михаил Артемович', '4010 100019', '+79000000019'),
    ('Крылова Дарья Владимировна', '4010 100020', '+79000000020')
ON CONFLICT (passport) DO NOTHING;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM products) THEN
        INSERT INTO products (
            bank_id,
            type_id,
            risk_id,
            currency_id,
            client_id,
            product_title,
            interest_rate,
            min_deposit,
            term_months,
            description,
            is_active
        )
        SELECT
            ((n - 1) % 10) + 1 AS bank_id,
            ((n - 1) % 4) + 1 AS type_id,
            CASE
                WHEN ((n - 1) % 4) + 1 = 3 THEN CASE WHEN n % 2 = 0 THEN 2 ELSE 3 END
                WHEN ((n - 1) % 4) + 1 = 4 THEN 2
                ELSE 1
            END AS risk_id,
            CASE
                WHEN n % 9 = 0 THEN 1
                WHEN n % 7 = 0 THEN 4
                WHEN n % 5 = 0 THEN 3
                ELSE 2
            END AS currency_id,
            CASE WHEN n % 3 = 0 THEN ((n - 1) % 20) + 1 ELSE NULL END AS client_id,
            (
                CASE ((n - 1) % 4) + 1
                    WHEN 1 THEN 'Вклад'
                    WHEN 2 THEN 'Счет'
                    WHEN 3 THEN 'ИИС'
                    ELSE 'Карта'
                END
                || ' №' || n
            ) AS product_title,
            CASE ((n - 1) % 4) + 1
                WHEN 1 THEN ROUND((10 + (n % 15) * 0.65)::numeric, 2)
                WHEN 2 THEN ROUND((6 + (n % 12) * 0.55)::numeric, 2)
                WHEN 3 THEN ROUND((8 + (n % 10) * 0.70)::numeric, 2)
                ELSE ROUND((0.1 + (n % 7) * 0.35)::numeric, 2)
            END AS interest_rate,
            CASE ((n - 1) % 4) + 1
                WHEN 1 THEN (10000 + (n % 8) * 25000)::numeric
                WHEN 2 THEN (0 + (n % 6) * 5000)::numeric
                WHEN 3 THEN (50000 + (n % 7) * 30000)::numeric
                ELSE (0 + (n % 5) * 1000)::numeric
            END AS min_deposit,
            CASE ((n - 1) % 4) + 1
                WHEN 1 THEN ((n % 6) + 1) * 6
                WHEN 2 THEN 0
                WHEN 3 THEN ((n % 4) + 1) * 12
                ELSE 0
            END AS term_months,
            'Сгенерированные данные для лабораторной работы' AS description,
            TRUE AS is_active
        FROM generate_series(1, 80) AS s(n);
    END IF;
END $$;
