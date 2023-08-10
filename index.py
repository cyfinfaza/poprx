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
    while True:
        message = await writeQueue.get()
        message["time"] = time.time()
        with open(filename, "a+") as logFile:
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
                if metadata["id"] in txGroupIds:
                    await websocket.send(error_json("txinit failed because another client is already using this ID"))
                    continue
                if len(json.dumps(metadata)) > 1024:
                    await websocket.send(error_json("txinit failed because metadata is too long"))
                    continue
                if not myId == "":
                    await websocket.send(error_json("txinit failed because the client already has an ID on the server"))
                    continue
                myId = metadata["id"]
                txGroupIds.add(myId)
                txGroupMetadata[myId] = metadata
                for ws in rxGroup:
                    await ws.send(
                        json.dumps(
                            {"type": "pop", "data": len(txGroupIds)})
                    )
                log = {"type": "txinit", **metadata}
                writeQueue.put_nowait(log)
                for ws in fullRxGroup:
                    await ws.send(json.dumps({"type": "log", "data": log}))
                await websocket.send(info_json("txinit success"))
            elif request["type"] == "pathUpdate":
                if myId != "":
                    txGroupMetadata[myId]["path"] = request["data"]
                    log = {
                        "type": "pathUpdate",
                        "id": myId,
                        "path": request["data"],
                    }
                    if request["data"] != txGroupMetadata[myId]["path"]:
                        writeQueue.put_nowait(log)
                    for ws in fullRxGroup:
                        await ws.send(json.dumps({"type": "log", "data": log}))
                    await websocket.send(info_json("pathUpdate success"))
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
