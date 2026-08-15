from anomaly import check_metric


print("CPU:", check_metric("cpu", 5))

print("CPU anomaly:", check_metric("cpu", 95))