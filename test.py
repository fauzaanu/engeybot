
import time

def count_bill():
    time_started = time.time()
    for i in range(1000000000):
        pass
    time_ended = time.time()
    return "Time elapsed: ", time_ended - time_started
    
    
for i in range(3):
    print(f'{i} : {count_bill()}')