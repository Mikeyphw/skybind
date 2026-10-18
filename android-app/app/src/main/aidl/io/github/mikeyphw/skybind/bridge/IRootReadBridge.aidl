package io.github.mikeyphw.skybind.bridge;

/** RootService exposes strictly allowlisted queries; never arbitrary commands. */
interface IRootReadBridge {
    String query(String operation, String arguments);
}
