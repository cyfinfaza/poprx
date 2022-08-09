import asyncio
import websockets
import json
import time
import sys

rxGroup = set()
fullRxGroup = set()
txGroupIds = set()
txGroupMetadata = {}


def error_json(message):
    return json.dumps({"type": "error", "data": message})


def info_json(message):
    return json.dumps({"type": "info", "data": message})


writeQueue = asyncio.Queue()
writeQueueEnabled = False


async def write_worker(filename):
    with open(filename, "a+") as logFile:
        while True:
            message = await writeQueue.get()
            message["time"] = time.time()
            logFile.write(json.dumps(message) + "\n")
            print("logged: " + json.dumps(message))
            writeQueue.task_done()


async def respond(websocket, path):
    print(path)
    rx = True
    fullRx = False
    myId = ""
    if path == "/txonly":
        rx = False
    if path == "/full":
        fullRx = True
        fullRxGroup.add(websocket)
        await websocket.send(json.dumps({"type": "metadata", "data": txGroupMetadata}))
    if rx:
        rxGroup.add(websocket)
        await websocket.send(json.dumps({"type": "pop", "data": len(txGroupIds)}))
    try:
        async for message in websocket:
            print(message)
            # try:
            request = json.loads(message)
            if request["type"] == "txinit":
                metadata = {
                    "id": str(request["data"]["id"]),
                    "agent": request["data"]["agent"],
                    "path": request["data"]["path"],
                }
                if (
                    not metadata["id"] in txGroupIds
                    and myId == ""
                    and len(json.dumps(metadata)) < 1024
                ):
                    myId = metadata["id"]
                    txGroupIds.add(myId)
                    txGroupMetadata[myId] = metadata
                    for ws in rxGroup:
                        await ws.send(
                            json.dumps({"type": "pop", "data": len(txGroupIds)})
                        )
                    log = {"type": "txinit", **metadata}
                    writeQueue.put_nowait(log)
                    for ws in fullRxGroup:
                        await ws.send(json.dumps({"type": "log", "data": log}))
                    await websocket.send(info_json("txinit success"))
                else:
                    await websocket.send(error_json("txinit failed"))
            elif request["type"] == "pathUpdate":
                if myId != "":
                    if request["data"] != txGroupMetadata[myId]["path"]:
                        txGroupMetadata[myId]["path"] = request["data"]
                        log = {
                            "type": "pathupdate",
                            "id": myId,
                            "path": request["data"],
                        }
                        writeQueue.put_nowait(log)
                        for ws in fullRxGroup:
                            await ws.send(json.dumps({"type": "log", "data": log}))
                        await websocket.send(info_json("pathUpdate success"))
                    else:
                        await websocket.send(
                            error_json("pathUpdate failed: attempted to set same path")
                        )
                else:
                    await websocket.send(error_json("user not initialized"))
            # except Exception as e:
            #     print(e)
            #     await websocket.send(error_json("invalid request"))
            #     continue
    finally:
        if rx:
            rxGroup.remove(websocket)
        if myId != "":
            txGroupIds.remove(myId)
            del txGroupMetadata[myId]
            for ws in rxGroup:
                await ws.send(json.dumps({"type": "pop", "data": len(txGroupIds)}))
            log = {"type": "disconnect", "id": myId}
            writeQueue.put_nowait(log)
            for ws in fullRxGroup:
                await ws.send(json.dumps({"type": "log", "data": log}))
        if fullRx:
            fullRxGroup.remove(websocket)


async def main():
    filename = "log.jsonl"
    if len(sys.argv) > 1:
        filename = sys.argv[1]
    asyncio.create_task(write_worker(filename))
    writeQueue.put_nowait({"type": "start"})
    async with websockets.serve(respond, "0.0.0.0", 6002):
        await asyncio.Future()  # run forever


asyncio.run(main())
