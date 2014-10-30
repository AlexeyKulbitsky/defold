(ns internal.system
  (:require [clojure.core.async :as a]
            [com.stuartsierra.component :as component]
            [dynamo.node :as n]
            [dynamo.types :as t]
            [schema.core :as s]
            [internal.bus :as bus]
            [internal.cache :refer [make-cache]]
            [internal.disposal :refer [disposal-message disposal-subsystem]]
            [internal.graph.dgraph :as dg]
            [internal.graph.lgraph :as lg]
            [internal.node :as in]
            [internal.refresh :refer [refresh-message refresh-subsystem]]
            [internal.transaction :refer [*scope*]]
            [service.log :as log :refer [logging-exceptions]]))

(set! *warn-on-reflection* true)

(defn graph [world-ref]
  (-> world-ref deref :graph))

(defn- attach-root
  [g r]
  (lg/add-labeled-node g (t/inputs r) (t/outputs r) r))

(defn new-world-state
  [state root]
   {:graph        (attach-root (dg/empty-graph) root)
    :cache        (make-cache)
    :cache-keys   {}
    :world-time   0
    :message-bus  (bus/make-bus)})

(defrecord World [started state]
  component/Lifecycle
  (start [this]
    (if (:started this)
      this
      (dosync
        (let [root (n/make-root :world-ref state :_id 1)]
          (ref-set state (new-world-state state root))
          (alter-var-root #'*scope* (constantly root))
          (assoc this :started true)))))
  (stop [this]
    (if (:started this)
      (dosync
        (ref-set state nil)
        (assoc this :started false))
      this)))

(defn- start-event-loop!
  [world-ref id in]
  (a/go-loop []
    (when-let [msg (a/<! in)]
      (try
        (t/process-one-event (dg/node (graph world-ref) id) msg)
        (catch Exception ex
          (service.log/error :message "Error in node event loop" :exception ex)))
      (recur))))

(defn- transaction-applied?
  [{old-world-time :world-time} {new-world-time :world-time :as new-world}]
  (and (:last-tx new-world) (< old-world-time new-world-time)))

(defn- start-event-loops
  [_ world-ref old-world {:keys [last-tx message-bus] :as new-world}]
  (when (transaction-applied? old-world new-world)
    (doseq [n (:new-event-loops last-tx)]
      (start-event-loop! world-ref n (bus/subscribe message-bus n)))))

(defn- send-tx-reports
  [report-ch _ _ old-world {last-tx :last-tx :as new-world}]
  (when (transaction-applied? old-world new-world)
    (a/put! report-ch last-tx)))

(defn- world
  [report-ch]
  (let [world-ref (ref nil)]
    (add-watch world-ref :tx-report   (partial send-tx-reports report-ch))
    (add-watch world-ref :event-loops start-event-loops)
    (->World false world-ref)))

(defn- disposal-messages
  [tx-report]
  (filter identity
    (for [v (:values-to-dispose tx-report)]
      (logging-exceptions "extracting disposal message"
        (disposal-message v)))))

(defn- refresh-messages
  [{:keys [expired-outputs graph]}]
  (filter identity
    (for [[node output] expired-outputs]
      (logging-exceptions "extracting refresh message"
        (refresh-message node graph output)))))

(defn- multiplex-reports
  [tx-report dispose refresh]
  (a/onto-chan dispose (disposal-messages tx-report) false)
  (a/onto-chan refresh (refresh-messages tx-report) false))

(defn shred-tx-reports
  [in]
  (let [dispose (a/chan (a/sliding-buffer 1000))
        refresh (a/chan (a/sliding-buffer 1000))]
    (a/go-loop []
      (let [tx-report (a/<! in)]
        (if tx-report
          (do
            (multiplex-reports tx-report dispose refresh)
            (recur))
          (do
            (a/close! dispose)
            (a/close! refresh)))))
    {:dispose dispose :refresh refresh}))

(defn system
 []
 (let [tx-report-chan (a/chan 1)
       {:keys [dispose refresh]} (shred-tx-reports tx-report-chan)]
   (component/map->SystemMap
     {:disposal  (disposal-subsystem dispose)
      :refresh   (refresh-subsystem  refresh)
      :world     (component/using (world tx-report-chan) [:disposal :refresh])})))

(def the-system (atom (system)))

(defn start
  ([]    (start the-system))
  ([sys] (swap! sys component/start-system)))

(defn stop
  ([]    (stop the-system))
  ([sys] (swap! sys component/stop-system)))
