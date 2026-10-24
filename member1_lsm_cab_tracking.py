import hashlib
import heapq
import time


class BloomFilter:
    def __init__(self, size=100, hash_count=3):
        self.size = size
        self.hash_count = hash_count
        self.bit_array = [False] * size

    def _hashes(self, item):
        return [
            int(hashlib.md5((str(item) + str(i)).encode()).hexdigest(), 16) % self.size
            for i in range(self.hash_count)
        ]

    def add(self, item):
        for h in self._hashes(item):
            self.bit_array[h] = True

    def check(self, item):
        return all(self.bit_array[h] for h in self._hashes(item))


class SSTable:
    def __init__(self, data):
        self.data = sorted(data.items())
        self.bloom_filter = BloomFilter()

        for k, _ in self.data:
            self.bloom_filter.add(k)

    def get(self, key):
        if not self.bloom_filter.check(key):
            return None

        low, high = 0, len(self.data) - 1

        while low <= high:
            mid = (low + high) // 2

            if self.data[mid][0] == key:
                return self.data[mid][1]
            elif self.data[mid][0] < key:
                low = mid + 1
            else:
                high = mid - 1

        return None


class LSMTree:
    def __init__(self, memtable_limit=5):
        self.memtable = {}
        self.memtable_limit = memtable_limit
        self.levels = [[]]

    def put(self, key, value):
        self.memtable[key] = value

        if len(self.memtable) >= self.memtable_limit:
            self.flush()

    def get(self, key):
        if key in self.memtable:
            val = self.memtable[key]
            return val if val != "TOMBSTONE" else None

        for level in self.levels:
            for sstable in reversed(level):
                val = sstable.get(key)

                if val is not None:
                    return val if val != "TOMBSTONE" else None

        return None

    def delete(self, key):
        self.put(key, "TOMBSTONE")

    def flush(self):
        if not self.memtable:
            return

        sstable = SSTable(self.memtable)
        self.levels[0].append(sstable)
        self.memtable = {}

        if len(self.levels[0]) >= 3:
            self.compact()

    def compact(self):
        heap = []

        for i, sstable in enumerate(self.levels[0]):
            if sstable.data:
                key, val = sstable.data[0]
                heapq.heappush(heap, (key, val, i, 0))

        merged_data = {}

        while heap:
            key, val, sst_idx, item_idx = heapq.heappop(heap)

            if key not in merged_data or sst_idx >= merged_data[key][1]:
                merged_data[key] = (val, sst_idx)

            next_idx = item_idx + 1

            if next_idx < len(self.levels[0][sst_idx].data):
                next_item = self.levels[0][sst_idx].data[next_idx]
                heapq.heappush(
                    heap,
                    (next_item[0], next_item[1], sst_idx, next_idx)
                )

        final_data = {
            k: v[0]
            for k, v in merged_data.items()
            if v[0] != "TOMBSTONE"
        }

        if len(self.levels) == 1:
            self.levels.append([])

        self.levels[1].append(SSTable(final_data))
        self.levels[0] = []

    def zone_range_query(self, zone_id):
        results = {}

        for k, v in self.memtable.items():
            if k.startswith(zone_id) and v != "TOMBSTONE":
                results[k] = v

        for level in self.levels:
            for sstable in reversed(level):
                for k, v in sstable.data:
                    if k.startswith(zone_id) and k not in results:
                        if v != "TOMBSTONE":
                            results[k] = v
                        else:
                            results[k] = None

        return {k: v for k, v in results.items() if v is not None}


def main():
    db = LSMTree(memtable_limit=5)

    while True:
        print("\n" + "=" * 40)
        print(" CAB DRIVER LOCATION TRACKING (LSM TREE)")
        print("=" * 40)
        print("1. Update Driver Location (Put / Ping)")
        print("2. Get Latest Driver Location (Get)")
        print("3. Find Drivers in a Zone (Range Query)")
        print("4. Mark Driver Offline (Delete / Tombstone)")
        print("5. View Database State (Internal Structure)")
        print("6. Exit")
        print("-" * 40)

        choice = input("Enter your choice (1-6): ")

        if choice == "1":
            zone = input("Enter Map Zone (e.g., ZONE_A): ").strip().upper()
            driver_id = input("Enter Driver ID (e.g., DRV_1): ").strip().upper()
            key = f"{zone}::{driver_id}"

            try:
                lat = float(input("Enter Latitude (e.g., 12.9716): "))
                lon = float(input("Enter Longitude (e.g., 77.5946): "))

                db.put(key, {
                    "lat": lat,
                    "lon": lon,
                    "timestamp": round(time.time(), 2)
                })

                print(f"\n[SUCCESS] Buffered location for {key} in Memtable.")

            except ValueError:
                print("\n[ERROR] Latitude and Longitude must be valid numbers.")

        elif choice == "2":
            zone = input("Enter Map Zone (e.g., ZONE_A): ").strip().upper()
            driver_id = input("Enter Driver ID (e.g., DRV_1): ").strip().upper()
            key = f"{zone}::{driver_id}"

            result = db.get(key)

            if result:
                print(f"\n[FOUND] Latest Location for {key}:")
                print(f"  Latitude:  {result['lat']}")
                print(f"  Longitude: {result['lon']}")
                print(f"  Timestamp: {result['timestamp']}")
            else:
                print(f"\n[NOT FOUND] Driver {key} is offline or does not exist.")

        elif choice == "3":
            zone = input("Enter Map Zone to scan (e.g., ZONE_A): ").strip().upper()
            drivers = db.zone_range_query(zone)

            if drivers:
                print(f"\n[ACTIVE DRIVERS IN {zone}]")

                for k, v in drivers.items():
                    print(f"  -> {k} | Lat: {v['lat']}, Lon: {v['lon']}")
            else:
                print(f"\n[EMPTY] No active drivers found in {zone}.")

        elif choice == "4":
            zone = input("Enter Map Zone (e.g., ZONE_A): ").strip().upper()
            driver_id = input("Enter Driver ID (e.g., DRV_1): ").strip().upper()
            key = f"{zone}::{driver_id}"

            db.delete(key)
            print(f"\n[SUCCESS] Driver {key} marked as offline (Tombstone written).")

        elif choice == "5":
            print("\n" + "-" * 20 + " SYSTEM STATE " + "-" * 20)
            print(f"Memtable (Current capacity {len(db.memtable)}/{db.memtable_limit}):")

            if not db.memtable:
                print("  (Empty)")

            for k, v in db.memtable.items():
                print(f"  {k}: {v}")

            print("\nDisk Storage (SSTables):")

            for i, level in enumerate(db.levels):
                print(f"  Level {i}: {len(level)} SSTable(s) stored.")

                for j, table in enumerate(level):
                    print(f"    SSTable {j} keys: {[k for k, _ in table.data]}")

            print("-" * 54)

        elif choice == "6":
            print("\nExiting system. Goodbye!")
            break

        else:
            print("\n[ERROR] Invalid choice. Please enter a number between 1 and 6.")


