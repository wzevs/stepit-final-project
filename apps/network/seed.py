"""Reference cities and districts. Tariffs and warehouses stay empty until a manager sets them."""

PLACES: list[tuple[str, list[str]]] = [
    (
        "თბილისი",
        [
            "ვაკე",
            "საბურთალო",
            "გლდანი",
            "ნაძალადევი",
            "ისანი",
            "სამგორი",
            "დიდუბე",
            "ჩუღურეთი",
            "კრწანისი",
            "მთაწმინდა",
        ],
    ),
    ("ბათუმი", ["ძველი ბათუმი", "ახალი ბულვარი", "აეროპორტი", "ბაგრატიონი"]),
    ("ქუთაისი", ["ცენტრი", "ავტოქარხანა", "საფიჩხია"]),
    ("რუსთავი", ["ძველი რუსთავი", "ახალი რუსთავი"]),
    ("ზუგდიდი", ["ცენტრი"]),
    ("ფოთი", ["ცენტრი"]),
    ("გორი", ["ცენტრი"]),
    ("თელავი", ["ცენტრი"]),
]


def load_places(city_model, district_model) -> None:
    for city_name, districts in PLACES:
        city, _ = city_model.objects.get_or_create(name=city_name)
        for name in districts:
            district_model.objects.get_or_create(city=city, name=name)
