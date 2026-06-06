import { BookOpen, Lightbulb, MessageSquare } from 'lucide-react'

export default function WelcomeHero() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-8 animate-fade-in">
      <div className="w-20 h-20 rounded-2xl bg-accent/10 flex items-center justify-center mb-6">
        <BookOpen className="w-10 h-10 text-accent" />
      </div>
      <h1 className="text-2xl font-semibold mb-3 text-white">
        Textbook RAG Tutor
      </h1>
      <p className="text-neutral-400 max-w-md mb-8 leading-relaxed">
        你的私人教材导师。基于检索增强生成（RAG），从教材中精准定位知识，
        用耐心和类比帮助你真正理解每一个概念。
      </p>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 w-full max-w-xl">
        {[
          {
            icon: Lightbulb,
            title: '提问学习',
            desc: '直接提问任何概念，导师从教材中找到答案',
          },
          {
            icon: MessageSquare,
            title: '对话交互',
            desc: '多轮对话，逐步深入理解知识点',
          },
          {
            icon: BookOpen,
            title: '出题练习',
            desc: '使用 /quiz 命令生成练习题检验掌握程度',
          },
        ].map((item) => (
          <div
            key={item.title}
            className="p-4 rounded-xl bg-neutral-900 border border-neutral-800 text-left"
          >
            <item.icon className="w-5 h-5 text-accent mb-2" />
            <h3 className="text-sm font-medium text-white mb-1">{item.title}</h3>
            <p className="text-xs text-neutral-500 leading-relaxed">
              {item.desc}
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}
