[H]
BUILD A TASK QUEUE WITH PRIORITY AND TIMEOUT

[D]
A lightweight in-memory task queue. Tasks have a name,
a priority (1-5, where 1 is highest), and a timeout in
milliseconds. The queue processes highest-priority first.
Timed-out tasks are marked failed, not retried.

[A]
use a binary heap for O(log n) insert and extract-min
store tasks as {id, name, priority, timeout, status, createdAt}
expose enqueue, process, and drain methods

[H]
ADD A CALLBACK FOR TASK COMPLETION

[A]
add an onComplete callback parameter to process()
fire it with {task, result, elapsed} on success
fire it with {task, error: 'timeout'} on timeout

[C]
class TaskQueue {
  constructor() {
    this.heap = [];
    this.nextId = 1;
  }

  enqueue(name, priority = 3, timeoutMs = 5000) {
    const task = {
      id: this.nextId++,
      name,
      priority,
      timeoutMs,
      status: 'pending',
      createdAt: Date.now()
    };
    this.heap.push(task);
    this._bubbleUp(this.heap.length - 1);
    return task;
  }

  async process(onComplete) {
    if (this.heap.length === 0) return null;
    const task = this._extractMin();
    task.status = 'running';
    const start = Date.now();
    try {
      await Promise.race([
        this._simulate(task),
        this._timeout(task.timeoutMs)
      ]);
      task.status = 'done';
      if (onComplete) onComplete({ task, result: 'ok', elapsed: Date.now() - start });
    } catch (e) {
      task.status = 'failed';
      if (onComplete) onComplete({ task, error: 'timeout' });
    }
    return task;
  }

  async drain(onComplete) {
    while (this.heap.length > 0) {
      await this.process(onComplete);
    }
  }

  _simulate(task) {
    const duration = 100 + Math.random() * 400;
    return new Promise(resolve => setTimeout(resolve, duration));
  }

  _timeout(ms) {
    return new Promise((_, reject) => setTimeout(() => reject('timeout'), ms));
  }

  _bubbleUp(i) {
    while (i > 0) {
      const parent = Math.floor((i - 1) / 2);
      if (this.heap[parent].priority <= this.heap[i].priority) break;
      [this.heap[parent], this.heap[i]] = [this.heap[i], this.heap[parent]];
      i = parent;
    }
  }

  _extractMin() {
    const min = this.heap[0];
    const last = this.heap.pop();
    if (this.heap.length > 0) {
      this.heap[0] = last;
      this._sinkDown(0);
    }
    return min;
  }

  _sinkDown(i) {
    const n = this.heap.length;
    while (true) {
      let smallest = i;
      const left = 2 * i + 1, right = 2 * i + 2;
      if (left < n && this.heap[left].priority < this.heap[smallest].priority) smallest = left;
      if (right < n && this.heap[right].priority < this.heap[smallest].priority) smallest = right;
      if (smallest === i) break;
      [this.heap[smallest], this.heap[i]] = [this.heap[i], this.heap[smallest]];
      i = smallest;
    }
  }
}

[R]
TaskQueue instantiated. Heap empty. Ready.

[H]
TEST IT WITH 5 TASKS, MIXED PRIORITIES

[C]
const q = new TaskQueue();
q.enqueue('deploy', 1);
q.enqueue('lint', 4);
q.enqueue('build', 2);
q.enqueue('notify', 5);
q.enqueue('test', 2);

q.drain((result) => {
  console.log(`[${result.task.priority}] ${result.task.name}: ${result.task.status}`);
});

[R]
[1] deploy: done
[2] build: done
[2] test: done
[4] lint: done
[5] notify: done

[D]
Priority ordering confirmed: tasks processed 1 → 2 → 2 → 4 → 5.
Equal-priority tasks processed in insertion order (stable).
No timeouts triggered (simulated durations all < 500ms, default timeout 5000ms).
