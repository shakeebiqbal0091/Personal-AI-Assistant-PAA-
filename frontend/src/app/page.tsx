
"use client";

// import { useState } from "react";
import { useState, useSyncExternalStore } from "react";

import {
  LayoutDashboard,
  MessageSquare,
  CheckSquare,
  History,
  Settings,
  Bot,
  Bell,
  Search,
  Plus,
  ArrowUpRight,
  CheckCircle2,
  Clock3,
  ListTodo,
  Sparkles,
  CalendarDays,
  MoreHorizontal,
  Menu,
  X,
  Send,
  ChevronRight,
  Zap,
  CircleUserRound,
} from "lucide-react";

const navigation = [
  { name: "Overview", icon: LayoutDashboard },
  { name: "AI Assistant", icon: MessageSquare },
  { name: "My Tasks", icon: CheckSquare },
  { name: "History", icon: History },
];

const initialTasks = [
  {
    id: 1,
    title: "Learn Next.js fundamentals",
    category: "Learning",
    time: "Today",
    completed: false,
  },
  {
    id: 2,
    title: "Review project architecture",
    category: "Development",
    time: "Today",
    completed: false,
  },
  {
    id: 3,
    title: "Build personal AI assistant",
    category: "Development",
    time: "Today",
    completed: true,
  },
];

function toLocalISODate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

const subscribeNoop = () => () => {};
const getLocalToday = (): string | null => toLocalISODate(new Date());
const getServerToday = (): string | null => null;

export default function Dashboard() {
  const [activePage, setActivePage] = useState("Overview");
  const [tasks, setTasks] = useState(initialTasks);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [chatInput, setChatInput] = useState("");
  const [chatMessages, setChatMessages] = useState<
   { id: number; text: string; sender: "user" | "assistant" }[]
  >([]);
  const today = useSyncExternalStore<string | null>(
    subscribeNoop,
    getLocalToday,
    getServerToday
  );
  const [pickedDate, setPickedDate] = useState<string | null>(null);
  const selectedDate = pickedDate ?? today;

  const [calendarOpen, setCalendarOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);


  const completed = tasks.filter((task) => task.completed).length;

  const addTask = () => {
    if (!message.trim()) return;

    setTasks((previous) => [
      ...previous,
      {
        id: Date.now(),
        title: message.trim(),
        category: "Personal",
        time: "Today",
        completed: false,
      },
    ]);

    setMessage("");
  };

  const toggleTask = (id: number) => {
    setTasks((previous) =>
      previous.map((task) =>
        task.id === id
          ? { ...task, completed: !task.completed }
          : task
      )
    );
  };

  const sidebar = (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-icon">
          <Bot size={23} />
        </div>
        <div>
          <h2>PAA</h2>
          <span>Personal Assistant</span>
        </div>
        <button
          className="mobile-close"
          onClick={() => setMobileOpen(false)}
          aria-label="Close menu"
        >
          <X size={20} />
        </button>
      </div>

      <div className="nav-section">
        <p className="nav-label">WORKSPACE</p>

        {navigation.map((item) => {
          const Icon = item.icon;

          return (
            <button
              key={item.name}
              className={`nav-item ${
                activePage === item.name ? "active" : ""
              }`}
              onClick={() => {
                setActivePage(item.name);
                setMobileOpen(false);
              }}
            >
              <Icon size={19} />
              <span>{item.name}</span>
              {item.name === "My Tasks" && (
                <span className="nav-count">{tasks.length}</span>
              )}
            </button>
          );
        })}
      </div>

      <div className="nav-section">
        <p className="nav-label">PREFERENCES</p>

        <button
          className={`nav-item ${
            activePage === "Settings" ? "active" : ""
          }`}
          onClick={() => {
            setActivePage("Settings");
            setMobileOpen(false);
          }}
        >
          <Settings size={19} />
          <span>Settings</span>
        </button>
      </div>

      <div className="sidebar-bottom">
        <div className="upgrade-card">
          <div className="upgrade-icon">
            <Zap size={17} />
          </div>
          <strong>Your productivity hub</strong>
          <p>Stay organized and get more done with PAA.</p>
          <span className="upgrade-link">
            Explore features <ArrowUpRight size={14} />
          </span>
        </div>

        <div className="profile">
          <div className="avatar">U</div>
          <div className="profile-info">
            <strong>Your Account</strong>
            <span>Personal Workspace</span>
          </div>
          <MoreHorizontal size={19} color="#64748b" />
        </div>
      </div>
    </aside>
  );

  return (
    <main className="app-shell">
      {mobileOpen && (
        <div
          className="mobile-overlay"
          onClick={() => setMobileOpen(false)}
        />
      )}

      <div className={`sidebar-wrapper ${mobileOpen ? "open" : ""}`}>
        {sidebar}
      </div>

      <section className="main-area">
        <header className="topbar">
          <div className="topbar-left">
            <button
              className="mobile-menu"
              onClick={() => setMobileOpen(true)}
              aria-label="Open menu"
            >
              <Menu size={21} />
            </button>

            <div className="breadcrumb">
              <span>Workspace</span>
              <ChevronRight size={15} />
              <strong>{activePage}</strong>
            </div>
          </div>

          <div className="topbar-right">
            <div className="search-box">
              <Search size={17} />
              <input placeholder="Search anything..." />
              <kbd>⌘ K</kbd>
            </div>


            <div className="dropdown-container">
  <button
    className="icon-button"
    aria-label="Notifications"
    onClick={() => {
      setNotificationsOpen(!notificationsOpen);
      setProfileOpen(false);
    }}
  >
    <Bell size={19} />
    <span className="notification-dot" />
  </button>

  {notificationsOpen && (
    <div className="dropdown-menu notification-menu">
      <h3>Notifications</h3>
      <div className="dropdown-item">
        <CheckCircle2 size={17} color="#16a34a" />
        <div>
          <strong>Welcome to PAA</strong>
          <span>Your assistant dashboard is ready.</span>
        </div>
      </div>
      <div className="dropdown-item">
        <Sparkles size={17} color="#5145e5" />
        <div>
          <strong>New features coming</strong>
          <span>AI chat integration is next.</span>
        </div>
      </div>
      <button
        className="dropdown-close"
        onClick={() => setNotificationsOpen(false)}
      >
        Close
      </button>
    </div>
  )}
</div>

            
<div className="dropdown-container">
  <button
    className="top-avatar profile-trigger"
    aria-label="Open profile menu"
    onClick={() => {
      setProfileOpen(!profileOpen);
      setNotificationsOpen(false);
    }}
  >
    U
  </button>

  {profileOpen && (
    <div className="dropdown-menu profile-menu">
      <div className="profile-menu-header">
        <div className="avatar">U</div>
        <div>
          <strong>Your Account</strong>
          <span>Personal Workspace</span>
        </div>
      </div>

      <button
        className="dropdown-option"
        onClick={() => {
          setActivePage("Settings");
          setProfileOpen(false);
        }}
      >
        <Settings size={17} />
        Settings
      </button>

      <button
        className="dropdown-option"
        onClick={() => setProfileOpen(false)}
      >
        <CircleUserRound size={17} />
        Close profile menu
      </button>
    </div>
  )}
</div>
          </div>
        </header>

        <div className="dashboard-content">
          <section className="welcome-section">
            <div>
              <div className="welcome-tag">
                <Sparkles size={14} />
                YOUR PERSONAL WORKSPACE
              </div>

              <h1>
                Good to see you! <span>👋</span>
              </h1>

              <p>
                Your day, your goals, your assistant. Let&apos;s make
                today productive.
              </p>
            </div>


            <div className="calendar-container">
  <button
    className="date-display"
    onClick={() => setCalendarOpen(!calendarOpen)}
    type="button"
  >
    <CalendarDays size={18} />
    <span>
    {selectedDate
     ? new Date(selectedDate + "T12:00:00").toLocaleDateString(
        "en-US",
        { weekday: "long", month: "long", day: "numeric" }
      )
      : "Today"}
    </span>
    <ChevronRight size={15} />
  </button>

  {calendarOpen && (
    <div className="calendar-dropdown">
      <label htmlFor="paa-calendar">Choose a date</label>
      <input
        id="paa-calendar"
        type="date"
        value={selectedDate ?? ""}
        onChange={(event) => setPickedDate(event.target.value || null)}
      />
      <button
        type="button"
        className="text-button"
        onClick={() => setCalendarOpen(false)}
      >
        Done
      </button>
    </div>
  )}
</div>
          </section>

          {activePage === "Overview" && (
            <>
              <section className="stats-grid">
                <div className="stat-card">
                  <div className="stat-top">
                    <div className="stat-icon purple">
                      <ListTodo size={21} />
                    </div>
                    <span className="stat-trend">
                      <ArrowUpRight size={14} />
                      Tasks
                    </span>
                  </div>
                  <h2>{tasks.length.toString().padStart(2, "0")}</h2>
                  <p>Total tasks</p>
                  <div className="stat-footer">Your task overview</div>
                </div>

                <div className="stat-card">
                  <div className="stat-top">
                    <div className="stat-icon green">
                      <CheckCircle2 size={21} />
                    </div>
                    <span className="stat-trend">Completed</span>
                  </div>
                  <h2>{completed.toString().padStart(2, "0")}</h2>
                  <p>Completed tasks</p>
                  <div className="stat-footer">
                    Keep up the great work!
                  </div>
                </div>

                <div className="stat-card">
                  <div className="stat-top">
                    <div className="stat-icon orange">
                      <Clock3 size={21} />
                    </div>
                    <span className="stat-trend">In progress</span>
                  </div>
                  <h2>
                    {(tasks.length - completed)
                      .toString()
                      .padStart(2, "0")}
                  </h2>
                  <p>Pending tasks</p>
                  <div className="stat-footer">
                    Tasks awaiting completion
                  </div>
                </div>

                <div className="stat-card">
                  <div className="stat-top">
                    <div className="stat-icon blue">
                      <MessageSquare size={21} />
                    </div>
                    <span className="stat-trend">AI powered</span>
                  </div>
                  <h2>AI</h2>
                  <p>Your assistant</p>
                  <div className="stat-footer">
                    Ready when you need it
                  </div>
                </div>
              </section>

              <section className="assistant-banner">
                <div className="assistant-banner-content">
                  <div className="ai-icon">
                    <Bot size={25} />
                  </div>

                  <div>
                    <div className="ai-status">
                      <span />
                      YOUR AI ASSISTANT IS READY
                    </div>

                    <h2>How can I help you today?</h2>

                    <p>
                      Ask me questions, organize your tasks,
                      or plan your day.
                    </p>
                  </div>
                </div>

                <button
                  className="primary-button"
                  onClick={() => setActivePage("AI Assistant")}
                >
                  Start a conversation
                  <ArrowUpRight size={17} />
                </button>
              </section>

              <section className="content-grid">
                <div className="panel tasks-panel">
                  <div className="panel-header">
                    <div>
                      <h3>Today&apos;s Tasks</h3>
                      <p>Keep track of what needs to get done.</p>
                    </div>

                    <button
                      className="text-button"
                      onClick={() => setActivePage("My Tasks")}
                    >
                      View all <ChevronRight size={16} />
                    </button>
                  </div>

                  <div className="task-list">
                    {tasks.map((task) => (
                      <div className="task-row" key={task.id}>
                        <button
                          className={`task-check ${
                            task.completed ? "checked" : ""
                          }`}
                          onClick={() => toggleTask(task.id)}
                          aria-label={`Toggle ${task.title}`}
                        >
                          {task.completed && (
                            <CheckCircle2 size={19} />
                          )}
                        </button>

                        <div className="task-info">
                          <strong
                            className={
                              task.completed ? "task-done" : ""
                            }
                          >
                            {task.title}
                          </strong>
                          <span>{task.category}</span>
                        </div>

                        <span
                          className={`task-status ${
                            task.completed ? "done" : ""
                          }`}
                        >
                          {task.completed ? "Completed" : task.time}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="panel activity-panel">
                  <div className="panel-header">
                    <div>
                      <h3>Quick Actions</h3>
                      <p>Get things done faster.</p>
                    </div>
                  </div>

                  <button
                    className="action-row"
                    onClick={() => setActivePage("AI Assistant")}
                  >
                    <div className="action-icon purple">
                      <MessageSquare size={19} />
                    </div>
                    <div>
                      <strong>Chat with AI</strong>
                      <span>Ask your assistant anything</span>
                    </div>
                    <ChevronRight size={17} />
                  </button>

                  <button
                    className="action-row"
                    onClick={() => setActivePage("My Tasks")}
                  >
                    <div className="action-icon green">
                      <Plus size={19} />
                    </div>
                    <div>
                      <strong>Manage tasks</strong>
                      <span>Organize your daily activities</span>
                    </div>
                    <ChevronRight size={17} />
                  </button>

                  <button
                    className="action-row"
                    onClick={() => setActivePage("History")}
                  >
                    <div className="action-icon orange">
                      <History size={19} />
                    </div>
                    <div>
                      <strong>View history</strong>
                      <span>Continue previous conversations</span>
                    </div>
                    <ChevronRight size={17} />
                  </button>
                </div>
              </section>
            </>
          )}

          {activePage === "My Tasks" && (
            <section className="panel full-panel">
              <div className="panel-header">
                <div>
                  <h3>My Tasks</h3>
                  <p>Manage your daily activities.</p>
                </div>
              </div>

              {tasks.map((task) => (
                <div className="task-row" key={task.id}>
                  <button
                    className={`task-check ${
                      task.completed ? "checked" : ""
                    }`}
                    onClick={() => toggleTask(task.id)}
                    aria-label={`Toggle ${task.title}`}
                  >
                    {task.completed && <CheckCircle2 size={19} />}
                  </button>
                  <div className="task-info">
                    <strong>{task.title}</strong>
                    <span>{task.category}</span>
                  </div>
                  <span className="task-status">
                    {task.completed ? "Completed" : "Pending"}
                  </span>
                </div>
              ))}

              <div className="add-task">
                <input
                  value={message}
                  onChange={(event) => setMessage(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") addTask();
                  }}
                  placeholder="Enter a new task..."
                />
                <button className="primary-button" onClick={addTask}>
                  <Plus size={17} /> Add task
                </button>
              </div>
            </section>
          )}


{activePage === "AI Assistant" && (
  <section className="panel chat-panel">
    <div className="chat-heading">
      <div className="chat-bot-icon">
        <Bot size={27} />
      </div>
      <div>
        <h2>Your AI Assistant</h2>
        <p>Start a conversation with PAA.</p>
      </div>
      <span className="demo-label">DEMO MODE</span>
    </div>

    <div className="chat-messages">
      {chatMessages.length === 0 && (
        <div className="chat-empty">
          <Sparkles size={27} />
          <h3>How can I help you today?</h3>
          <p>
            Write a message below to start your conversation.
          </p>
        </div>
      )}

      {chatMessages.map((item) => (
        <div
          key={item.id}
          className={`chat-message ${
            item.sender === "user" ? "user-message" : "assistant-message"
          }`}
        >
          <span>{item.sender === "user" ? "You" : "PAA"}</span>
          <p>{item.text}</p>
        </div>
      ))}
    </div>

    <form
      className="chat-input-area"
      onSubmit={(event) => {
        event.preventDefault();

        if (!chatInput.trim()) return;

        setChatMessages((previous) => [
          ...previous,
          {
            id: Date.now(),
            text: chatInput.trim(),
            sender: "user",
          },
        ]);

        setChatInput("");
      }}
    >
      <input
        type="text"
        value={chatInput}
        onChange={(event) => setChatInput(event.target.value)}
        placeholder="Ask PAA anything..."
        aria-label="Write a message"
      />

      <button
        type="submit"
        className="send-button"
        disabled={!chatInput.trim()}
        aria-label="Send message"
      >
        <Send size={18} />
      </button>
    </form>

    <p className="chat-disclaimer">
      Frontend demo: messages are not yet connected to your AI backend.
    </p>
  </section>
)}

          {activePage === "History" && (
            <section className="panel full-panel">
              <History size={28} color="#64748b" />
              <h3>Conversation History</h3>
              <p>
                Your saved conversations will appear here
                when the Python backend is connected.
              </p>
            </section>
          )}

          {activePage === "Settings" && (
            <section className="panel full-panel">
              <Settings size={28} color="#64748b" />
              <h3>Settings</h3>
              <p>Application preferences will be available here.</p>
            </section>
          )}

          <footer className="footer">
            <span>© 2026 PAA · Personal AI Assistant</span>
            <span className="footer-status">
              <span /> System operational
            </span>
          </footer>
        </div>
      </section>
    </main>
  );
}