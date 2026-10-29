from apps.shipments.models import Shipment

STATUS_KA = {
    Shipment.Status.DRAFT: "დრაფტი",
    Shipment.Status.PENDING: "ელოდება აღებას",
    Shipment.Status.ASSIGNED: "კურიერი დანიშნულია",
    Shipment.Status.PICKED_UP: "აღებულია",
    Shipment.Status.IN_TRANSIT: "გზაშია",
    Shipment.Status.OUT_FOR_DELIVERY: "მიაქვთ მიმღებთან",
    Shipment.Status.DELIVERED: "ჩაბარებულია",
    Shipment.Status.FAILED: "ვერ ჩაბარდა",
    Shipment.Status.RETURNED: "დაბრუნებულია",
    Shipment.Status.CANCELLED: "გაუქმებულია",
}
