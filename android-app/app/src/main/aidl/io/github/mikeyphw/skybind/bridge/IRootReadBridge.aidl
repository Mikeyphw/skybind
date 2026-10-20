package io.github.mikeyphw.skybind.bridge;

/** App-private, root-manager-approved. Mutations require a server-bound preview. */
interface IRootReadBridge {
    String query(String operation, String arguments);
    String previewJob(String sessionId, String jobName);
    String startPreparedJob(String sessionId, String previewId);
    String cancelOwnedRun(String sessionId, String runId);
    void forgetSession(String sessionId);
}
